# Production Architecture Part 2 - Training, Security, Scaling

## Training Pipeline Management

### Continuous Training System

```python
# services/training/orchestrator.py
from datetime import datetime, timedelta
import mlflow
from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import EvalCallback, CheckpointCallback

class TrainingOrchestrator:
    """
    Manages continuous training of digital twin agents
    """
    
    def __init__(self, profile_id: str):
        self.profile_id = profile_id
        self.mlflow_tracking_uri = "postgresql://..."
        mlflow.set_tracking_uri(self.mlflow_tracking_uri)
        
    async def should_trigger_training(self) -> bool:
        """
        Decide if training should be triggered
        """
        # Get user's response count
        response_count = await self.get_response_count()
        last_training = await self.get_last_training_time()
        
        # Trigger conditions:
        # 1. New user: train after 100 responses
        if response_count == 100:
            return True
        
        # 2. Regular user: train every 500 new responses
        responses_since_last = await self.get_responses_since(last_training)
        if responses_since_last >= 500:
            return True
        
        # 3. Weekly retraining for active users
        if last_training < datetime.now() - timedelta(days=7):
            if responses_since_last >= 50:  # Some new data
                return True
        
        return False
    
    async def train_agent(self, config: dict):
        """
        Train the agent with MLflow tracking
        """
        with mlflow.start_run(run_name=f"{self.profile_id}_{datetime.now().isoformat()}"):
            
            # Log parameters
            mlflow.log_params(config)
            
            # Prepare environment
            env = await self.prepare_environment()
            
            # Initialize or load agent
            if await self.has_existing_model():
                agent = PPO.load(
                    await self.get_latest_model_path(),
                    env=env
                )
            else:
                agent = PPO("MultiInputPolicy", env, **config)
            
            # Setup callbacks
            checkpoint_callback = CheckpointCallback(
                save_freq=10000,
                save_path=f"./models/{self.profile_id}/",
                name_prefix="digital_twin"
            )
            
            eval_callback = EvalCallback(
                eval_env=env,
                best_model_save_path=f"./models/{self.profile_id}/best/",
                log_path=f"./logs/{self.profile_id}/",
                eval_freq=5000,
                deterministic=True,
                render=False
            )
            
            # Train
            agent.learn(
                total_timesteps=config['total_timesteps'],
                callback=[checkpoint_callback, eval_callback],
                progress_bar=True
            )
            
            # Log metrics
            mlflow.log_metric("total_timesteps", config['total_timesteps'])
            
            # Save final model
            model_version = await self.save_model(agent)
            mlflow.log_param("model_version", model_version)
            
            # Run validation
            validation_score = await self.validate_model(agent)
            mlflow.log_metric("validation_score", validation_score)
            
            # Update database
            await self.update_model_registry(model_version, validation_score)
            
            return model_version

    async def validate_model(self, agent) -> float:
        """
        Validate agent against known user choices
        Generate validation questions for user
        """
        # Get held-out test scenarios
        test_scenarios = await self.get_test_scenarios(n=100)
        
        correct_predictions = 0
        for scenario in test_scenarios:
            # Get agent prediction
            agent_action = agent.predict(scenario['state'])[0]
            
            # Compare to user's actual choice
            if agent_action == scenario['user_choice']:
                correct_predictions += 1
        
        accuracy = correct_predictions / len(test_scenarios)
        
        # Generate new validation questions for user
        await self.generate_validation_questions(agent, n=10)
        
        return accuracy


class ModelVersioning:
    """
    Manage model versions with gradual rollout
    """
    
    async def deploy_new_version(self, model_version: str):
        """
        Deploy new model with canary rollout
        """
        # Stage 1: Canary (5% of predictions)
        await self.set_traffic_split({
            'current': 0.95,
            model_version: 0.05
        })
        
        # Monitor for 24 hours
        await self.monitor_canary(model_version, hours=24)
        
        # Stage 2: 50% traffic
        metrics = await self.get_canary_metrics(model_version)
        if metrics['validation_score'] > await self.get_current_model_score():
            await self.set_traffic_split({
                'current': 0.50,
                model_version: 0.50
            })
            
            # Monitor for 48 hours
            await self.monitor_rollout(model_version, hours=48)
        
        # Stage 3: Full rollout
        metrics = await self.get_rollout_metrics(model_version)
        if metrics['user_satisfaction'] >= 0.8:
            await self.set_traffic_split({
                model_version: 1.0
            })
            
            # Mark as current
            await self.set_as_current_model(model_version)
        else:
            # Rollback
            await self.rollback_to_previous()
    
    async def rollback_to_previous(self):
        """
        Instant rollback to previous stable version
        """
        previous_version = await self.get_previous_stable_version()
        await self.set_traffic_split({
            previous_version: 1.0
        })
        
        # Log rollback event
        await self.log_rollback_event()


# Scheduled training job
from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler()

@scheduler.scheduled_job('interval', hours=6)
async def check_training_triggers():
    """
    Check all users and trigger training if needed
    """
    active_users = await get_active_users()
    
    for user in active_users:
        orchestrator = TrainingOrchestrator(user.id)
        
        if await orchestrator.should_trigger_training():
            # Queue training job
            await queue_training_job(user.id)

scheduler.start()
```

### Model Registry & Versioning

```sql
-- Track all model versions
CREATE TABLE model_registry (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    profile_id UUID REFERENCES profiles(id),
    version TEXT NOT NULL,
    storage_path TEXT NOT NULL,
    
    -- Training metadata
    training_steps INTEGER,
    total_reward REAL,
    training_duration_seconds INTEGER,
    
    -- Performance metrics
    validation_score REAL,
    user_validation_score REAL,  -- From user feedback
    accuracy_score REAL,
    
    -- Deployment status
    status TEXT DEFAULT 'trained',  -- 'trained', 'canary', 'production', 'archived'
    traffic_percentage REAL DEFAULT 0.0,
    
    -- Timestamps
    trained_at TIMESTAMPTZ DEFAULT NOW(),
    deployed_at TIMESTAMPTZ,
    archived_at TIMESTAMPTZ,
    
    -- MLflow reference
    mlflow_run_id TEXT,
    
    metadata JSONB,
    
    UNIQUE(profile_id, version)
);

-- Model performance tracking
CREATE TABLE model_predictions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    profile_id UUID REFERENCES profiles(id),
    model_version TEXT,
    scenario_id UUID,
    predicted_action JSONB,
    actual_user_action JSONB,
    was_correct BOOLEAN,
    confidence_score REAL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_model_registry_profile_status 
    ON model_registry(profile_id, status);
    
CREATE INDEX idx_model_predictions_version 
    ON model_predictions(model_version, created_at DESC);
```

## Data Backup & Recovery

### Backup Strategy

```typescript
// apps/web/lib/backup.ts

/**
 * Multi-layer backup strategy
 */

// Layer 1: Supabase automated backups (built-in)
// - Daily automated backups
// - 7-day point-in-time recovery
// - Stored in S3

// Layer 2: Weekly full exports to external storage
import { createClient } from '@supabase/supabase-js';
import { S3Client, PutObjectCommand } from '@aws-sdk/client-s3';

export async function weeklyFullBackup(profileId: string) {
  const supabase = createClient(
    process.env.SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!
  );
  
  // Export all user data
  const { data: responses } = await supabase
    .from('responses')
    .select('*')
    .eq('profile_id', profileId);
    
  const { data: patterns } = await supabase
    .from('patterns')
    .select('*')
    .eq('profile_id', profileId);
    
  const { data: entities } = await supabase
    .from('entities')
    .select('*')
    .eq('profile_id', profileId);
  
  const backup = {
    version: '1.0',
    timestamp: new Date().toISOString(),
    profileId,
    data: {
      responses,
      patterns,
      entities,
    }
  };
  
  // Upload to S3 (or Cloudflare R2 for cheaper storage)
  const s3 = new S3Client({ region: 'us-east-1' });
  
  await s3.send(new PutObjectCommand({
    Bucket: 'digital-twin-backups',
    Key: `${profileId}/weekly/${new Date().toISOString()}.json.gz`,
    Body: gzip(JSON.stringify(backup)),
    StorageClass: 'GLACIER_IR',  // Cheap long-term storage
  }));
  
  // Keep last 52 weekly backups (1 year)
  await cleanupOldBackups(profileId, keepLast: 52);
}

// Layer 3: Real-time replication to secondary database
// Use Supabase read replicas or pg_basebackup

// Layer 4: User-initiated exports
export async function exportUserData(profileId: string): Promise<Blob> {
  // Complete data export in portable format
  const data = await fetchAllUserData(profileId);
  
  return new Blob([JSON.stringify(data, null, 2)], {
    type: 'application/json'
  });
}
```

### Disaster Recovery Plan

```yaml
# disaster-recovery.yml

# Recovery Time Objective (RTO): 4 hours
# Recovery Point Objective (RPO): 1 hour

procedures:
  database_failure:
    detection:
      - Automated health checks every 60 seconds
      - Alert via PagerDuty if 3 consecutive failures
    
    recovery:
      1. Switch DNS to read replica (automated)
      2. Promote read replica to primary
      3. Restore from latest backup if needed
      4. Verify data integrity
      5. Resume normal operations
    
    estimated_time: "2 hours"
  
  vercel_outage:
    detection:
      - Vercel status page monitoring
      - Health check failures
    
    recovery:
      1. Deploy to backup Cloudflare Pages
      2. Update DNS CNAME
      3. Traffic redirected within 5 minutes
    
    estimated_time: "30 minutes"
  
  training_service_failure:
    detection:
      - Training job monitoring
      - Failed job alerts
    
    recovery:
      1. Training is non-critical, can wait
      2. Restart failed jobs
      3. Users continue with existing models
    
    estimated_time: "No immediate action needed"
  
  data_corruption:
    detection:
      - Integrity checks in CI/CD
      - User reports
    
    recovery:
      1. Identify corruption timestamp
      2. Point-in-time recovery to before corruption
      3. Replay transactions if possible
      4. Notify affected users
    
    estimated_time: "4 hours"

testing:
  frequency: "Quarterly"
  scope: "Full disaster recovery drill"
  documentation: "Update runbook after each drill"
```

## Security & Privacy

### Authentication & Authorization

```typescript
// apps/web/lib/auth.ts
import { createClient } from '@supabase/supabase-js';

// Supabase Auth configuration
export const supabase = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL!,
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
  {
    auth: {
      autoRefreshToken: true,
      persistSession: true,
      detectSessionInUrl: true,
      flowType: 'pkce',  // More secure than implicit flow
    }
  }
);

// Multi-factor authentication
export async function enableMFA(userId: string) {
  const { data, error } = await supabase.auth.mfa.enroll({
    factorType: 'totp',
  });
  
  return data;
}

// Biometric auth for mobile
export async function enableBiometric() {
  // React Native: expo-local-authentication
  const hasHardware = await LocalAuthentication.hasHardwareAsync();
  const isEnrolled = await LocalAuthentication.isEnrolledAsync();
  
  if (hasHardware && isEnrolled) {
    const result = await LocalAuthentication.authenticateAsync({
      promptMessage: 'Authenticate to access your digital twin',
      fallbackLabel: 'Use passcode',
    });
    
    return result.success;
  }
  
  return false;
}
```

### Data Encryption

```sql
-- Encrypt sensitive data at rest
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Encrypt PII before storage
CREATE OR REPLACE FUNCTION encrypt_pii()
RETURNS TRIGGER AS $$
BEGIN
  IF NEW.phone_number IS NOT NULL THEN
    NEW.phone_number = pgp_sym_encrypt(
      NEW.phone_number,
      current_setting('app.encryption_key')
    );
  END IF;
  
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply to entities table
CREATE TRIGGER encrypt_entity_pii
  BEFORE INSERT OR UPDATE ON entities
  FOR EACH ROW
  EXECUTE FUNCTION encrypt_pii();
```

```typescript
// Client-side encryption for ultra-sensitive data
import { encrypt, decrypt } from '@/lib/crypto';

export async function storeEncrypted(key: string, data: any) {
  // Encrypt on client before sending to server
  const encrypted = await encrypt(data, userDerivedKey);
  
  await supabase
    .from('encrypted_data')
    .insert({ key, data: encrypted });
}

// Only user can decrypt (server never sees plaintext)
export async function retrieveEncrypted(key: string) {
  const { data } = await supabase
    .from('encrypted_data')
    .select('data')
    .eq('key', key)
    .single();
  
  return await decrypt(data.data, userDerivedKey);
}
```

### Privacy Controls

```typescript
// apps/web/app/api/privacy/route.ts

/**
 * GDPR/CCPA compliance endpoints
 */

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const action = searchParams.get('action');
  
  switch (action) {
    case 'export':
      // Right to data portability
      return await exportAllUserData();
      
    case 'delete':
      // Right to be forgotten
      return await deleteAllUserData();
      
    case 'restrict':
      // Right to restrict processing
      return await restrictDataProcessing();
      
    default:
      return new Response('Invalid action', { status: 400 });
  }
}

async function deleteAllUserData() {
  const userId = await getCurrentUserId();
  
  // Cascade delete all user data
  await supabase.from('responses').delete().eq('profile_id', userId);
  await supabase.from('patterns').delete().eq('profile_id', userId);
  await supabase.from('entities').delete().eq('profile_id', userId);
  await supabase.from('model_versions').delete().eq('profile_id', userId);
  
  // Delete stored models
  await deleteModelsFromStorage(userId);
  
  // Anonymize in logs (can't delete logs completely)
  await anonymizeUserInLogs(userId);
  
  // Delete auth account
  await supabase.auth.admin.deleteUser(userId);
  
  return new Response('All data deleted', { status: 200 });
}

// Privacy-preserving analytics
export function trackEvent(event: string, properties?: object) {
  // Hash user ID before sending to analytics
  const anonymousId = hashUserId(userId);
  
  posthog.capture(event, {
    ...properties,
    distinct_id: anonymousId,
    $set: {
      anonymized: true,
    }
  });
}
```

## Cost Optimization (10-Year Plan)

### Current Costs (Per User/Month)

```yaml
# Year 1 (MVP - First 1000 users)
infrastructure:
  vercel:
    hobby: $0/month (free tier)
    pro: $20/month (when needed)
    usage: ~$5/month per 1000 users
    
  supabase:
    free: $0/month (up to 500MB, 50K MAU)
    pro: $25/month (8GB, 100K MAU)
    
  railway:
    starter: $5/month
    usage: ~$0.01 per training hour
    
  cloudflare:
    free: $0/month (unlimited bandwidth)
    
  monitoring:
    sentry: $26/month (50K events)
    posthog: $0/month (self-hosted)
    betteruptime: $10/month
    
  storage:
    cloudflare_r2: $0.015/GB/month
    
total_monthly: ~$70-100/month
cost_per_user: $0.07-0.10/month

# Year 3 (Growth - 10,000 users)
infrastructure:
  vercel_pro: $20/month
  vercel_usage: $50/month
  supabase_pro: $25/month
  supabase_compute: $100/month (dedicated CPU)
  railway: $50/month (GPU for training)
  cloudflare_pro: $20/month
  monitoring: $100/month
  storage: $50/month
  
total_monthly: ~$415/month
cost_per_user: $0.04/month
revenue_target: $5/user/month = $50K/month

# Year 5 (Scale - 100,000 users)
infrastructure:
  vercel_enterprise: $2000/month
  supabase_enterprise: $1000/month
  training_cluster: $500/month
  monitoring: $500/month
  cdn: $100/month
  storage: $500/month
  
total_monthly: ~$4600/month
cost_per_user: $0.046/month
revenue_target: $3/user/month = $300K/month
```

### Optimization Strategies

```typescript
// Cost optimization techniques

// 1. Lazy training
// Don't train inactive users
async function shouldTrainUser(userId: string): Promise<boolean> {
  const lastActive = await getLastActiveDate(userId);
  const daysSinceActive = daysBetween(lastActive, new Date());
  
  if (daysSinceActive > 30) {
    return false;  // Skip training for inactive users
  }
  
  return true;
}

// 2. Batch processing
// Train multiple users in single GPU session
async function batchTraining() {
  const usersToTrain = await getUsersNeedingTraining();
  
  // Train in batches of 10 to amortize GPU startup cost
  for (const batch of chunk(usersToTrain, 10)) {
    await trainBatch(batch);
  }
}

// 3. Progressive data retention
// Older data compressed and moved to cheaper storage
async function archiveOldData() {
  // Keep last 90 days in hot storage
  const cutoffDate = new Date(Date.now() - 90 * 24 * 60 * 60 * 1000);
  
  // Move older data to Cloudflare R2 (90% cheaper)
  const oldData = await supabase
    .from('responses')
    .select('*')
    .lt('created_at', cutoffDate.toISOString());
  
  await uploadToR2('archived-responses', oldData);
  await supabase.from('responses').delete().lt('created_at', cutoffDate);
}

// 4. CDN optimization
// Cache aggressively
export const revalidate = 3600;  // 1 hour cache for static content
export const dynamic = 'force-static';

// 5. Database query optimization
// Use database indexes and materialized views
CREATE MATERIALIZED VIEW user_stats AS
SELECT 
  profile_id,
  COUNT(*) as response_count,
  MAX(created_at) as last_response,
  AVG(response_time_ms) as avg_response_time
FROM responses
GROUP BY profile_id;

-- Refresh nightly
REFRESH MATERIALIZED VIEW CONCURRENTLY user_stats;
```

## Scaling Strategy (2026-2036)

### Phase 1: MVP (0-1K users) - Year 1
```yaml
focus: "Product-market fit"
infrastructure: "Free tiers + minimal paid"
priorities:
  - Ship fast
  - Gather feedback
  - Iterate quickly
  
costs: $100/month
team: 1-2 people
```

### Phase 2: Growth (1K-10K users) - Years 2-3
```yaml
focus: "Optimize core metrics"
infrastructure: "Upgrade to Pro tiers"
priorities:
  - Performance optimization
  - User retention
  - Training efficiency
  
costs: $500/month
team: 2-3 people
revenue: $50K/month (@$5/user)
```

### Phase 3: Scale (10K-100K users) - Years 4-5
```yaml
focus: "Horizontal scaling"
infrastructure: "Enterprise contracts + dedicated resources"
priorities:
  - Multi-region deployment
  - 99.9% uptime SLA
  - Advanced features
  
costs: $5K/month
team: 5-8 people
revenue: $300K/month (@$3/user)
```

### Phase 4: Maturity (100K-1M users) - Years 6-10
```yaml
focus: "Platform optimization"
infrastructure: "Custom infrastructure + managed services"
priorities:
  - Cost per user reduction
  - Advanced AI capabilities
  - International expansion
  
costs: $30K/month
team: 15-20 people
revenue: $2M/month (@$2/user)
```

### Technical Evolution

```yaml
2026-2027: Foundation
  - Supabase PostgreSQL
  - Vercel hosting
  - Railway training
  - Stable-Baselines3

2028-2029: Optimization
  - Read replicas
  - GPU training optimization
  - Advanced caching
  - Custom algorithms

2030-2032: Scale
  - Multi-region deployment
  - Custom training infrastructure
  - Real-time collaboration features
  - API platform for developers

2033-2036: Innovation
  - On-device AI (local training)
  - Quantum computing experiments
  - Brain-computer interfaces
  - Federation/decentralization
```

Ready for Part 3 with environment configs, deployment scripts, and detailed cost projections?
