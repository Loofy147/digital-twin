# ============================================
# COMPLETE DEPLOYMENT CONFIGURATION
# ============================================

# ============================================
# 1. PROJECT INITIALIZATION
# ============================================

#!/bin/bash
# setup.sh - Complete project setup script

echo "🚀 Setting up Digital Twin System..."

# Check prerequisites
command -v node >/dev/null 2>&1 || { echo "Node.js required but not installed."; exit 1; }
command -v pnpm >/dev/null 2>&1 || { echo "pnpm required. Installing..."; npm install -g pnpm; }
command -v python3 >/dev/null 2>&1 || { echo "Python 3 required but not installed."; exit 1; }

# Create project structure
echo "📁 Creating project structure..."
mkdir -p digital-twin/{apps,packages,services}
cd digital-twin

# Initialize monorepo
cat > package.json << 'EOF'
{
  "name": "digital-twin",
  "private": true,
  "workspaces": [
    "apps/*",
    "packages/*"
  ],
  "scripts": {
    "dev": "turbo run dev",
    "build": "turbo run build",
    "test": "turbo run test",
    "lint": "turbo run lint",
    "deploy": "./scripts/deploy.sh"
  },
  "devDependencies": {
    "turbo": "^2.0.0",
    "typescript": "^5.3.0"
  }
}
EOF

# Initialize Turbo
cat > turbo.json << 'EOF'
{
  "$schema": "https://turbo.build/schema.json",
  "globalDependencies": ["**/.env.*local"],
  "pipeline": {
    "build": {
      "dependsOn": ["^build"],
      "outputs": [".next/**", "dist/**"]
    },
    "dev": {
      "cache": false,
      "persistent": true
    },
    "test": {
      "dependsOn": ["build"],
      "outputs": ["coverage/**"]
    },
    "lint": {
      "outputs": []
    }
  }
}
EOF

# ============================================
# 2. WEB APP SETUP (Next.js)
# ============================================

echo "🌐 Setting up Web App..."
cd apps
npx create-next-app@latest web \
  --typescript \
  --tailwind \
  --app \
  --src-dir \
  --import-alias "@/*" \
  --use-pnpm

cd web

# Install dependencies
pnpm add @supabase/supabase-js @supabase/auth-helpers-nextjs
pnpm add zustand @tanstack/react-query
pnpm add zod
pnpm add recharts lucide-react
pnpm add -D @types/node

# Environment template
cat > .env.local.example << 'EOF'
# Supabase
NEXT_PUBLIC_SUPABASE_URL=your_supabase_url
NEXT_PUBLIC_SUPABASE_ANON_KEY=your_supabase_anon_key
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key

# Training API
TRAINING_API_URL=your_training_api_url
TRAINING_API_KEY=your_api_key

# Monitoring
NEXT_PUBLIC_SENTRY_DSN=your_sentry_dsn
NEXT_PUBLIC_POSTHOG_KEY=your_posthog_key

# Google OAuth (for integrations)
GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret
EOF

# Next.js config
cat > next.config.js << 'EOF'
/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  swcMinify: true,
  experimental: {
    serverActions: true,
  },
  images: {
    domains: ['your-supabase-project.supabase.co'],
  },
  webpack: (config, { isServer }) => {
    if (!isServer) {
      config.resolve.fallback = {
        ...config.resolve.fallback,
        fs: false,
        net: false,
        tls: false,
      };
    }
    return config;
  },
}

module.exports = nextConfig
EOF

# TypeScript config
cat > tsconfig.json << 'EOF'
{
  "compilerOptions": {
    "target": "ES2020",
    "lib": ["dom", "dom.iterable", "esnext"],
    "allowJs": true,
    "skipLibCheck": true,
    "strict": true,
    "forceConsistentCasingInFileNames": true,
    "noEmit": true,
    "esModuleInterop": true,
    "module": "esnext",
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "jsx": "preserve",
    "incremental": true,
    "plugins": [
      {
        "name": "next"
      }
    ],
    "paths": {
      "@/*": ["./src/*"]
    }
  },
  "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx", ".next/types/**/*.ts"],
  "exclude": ["node_modules"]
}
EOF

cd ../..

# ============================================
# 3. TRAINING SERVICE SETUP (Python)
# ============================================

echo "🤖 Setting up Training Service..."
mkdir -p services/training
cd services/training

# Requirements
cat > requirements.txt << 'EOF'
fastapi==0.109.0
uvicorn[standard]==0.27.0
stable-baselines3==2.2.1
gymnasium==0.29.1
torch==2.1.2
sqlalchemy==2.0.25
asyncpg==0.29.0
pydantic==2.5.3
pydantic-settings==2.1.0
python-multipart==0.0.6
mlflow==2.10.0
ray[default]==2.9.0
apscheduler==3.10.4
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
python-dotenv==1.0.0
EOF

# Environment template
cat > .env.example << 'EOF'
# Database
DATABASE_URL=postgresql://user:password@host:5432/dbname

# MLflow
MLFLOW_TRACKING_URI=postgresql://user:password@host:5432/mlflow

# Storage
MODEL_STORAGE_PATH=/models
CHECKPOINT_STORAGE_PATH=/checkpoints

# API
API_HOST=0.0.0.0
API_PORT=8000
SECRET_KEY=your-secret-key

# Training Config
MAX_PARALLEL_TRAINING_JOBS=5
GPU_ENABLED=false
EOF

# Main FastAPI app
cat > main.py << 'EOF'
from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import uvicorn

app = FastAPI(title="Digital Twin Training API", version="1.0.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure properly in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class TrainingRequest(BaseModel):
    profile_id: str
    config: dict = {
        "total_timesteps": 100000,
        "learning_rate": 3e-4,
        "n_steps": 2048,
        "batch_size": 64,
    }

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

@app.post("/train")
async def start_training(
    request: TrainingRequest,
    background_tasks: BackgroundTasks
):
    """Start training a digital twin agent"""
    from orchestrator import TrainingOrchestrator
    
    orchestrator = TrainingOrchestrator(request.profile_id)
    
    # Queue training job
    background_tasks.add_task(
        orchestrator.train_agent,
        request.config
    )
    
    return {
        "status": "training_queued",
        "profile_id": request.profile_id,
        "message": "Training job started in background"
    }

@app.get("/status/{profile_id}")
async def get_training_status(profile_id: str):
    """Get current training status"""
    # Implementation here
    return {
        "profile_id": profile_id,
        "status": "training",
        "progress": 0.45,
        "current_step": 45000,
        "total_steps": 100000,
    }

@app.get("/models/{profile_id}")
async def list_models(profile_id: str):
    """List all model versions for a user"""
    # Implementation here
    return {
        "profile_id": profile_id,
        "models": []
    }

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
EOF

# Dockerfile
cat > Dockerfile << 'EOF'
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

# Run
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
EOF

# Railway config
cat > railway.json << 'EOF'
{
  "$schema": "https://railway.app/railway.schema.json",
  "build": {
    "builder": "DOCKERFILE"
  },
  "deploy": {
    "startCommand": "uvicorn main:app --host 0.0.0.0 --port $PORT",
    "healthcheckPath": "/health",
    "healthcheckTimeout": 100,
    "restartPolicyType": "ON_FAILURE"
  }
}
EOF

cd ../..

# ============================================
# 4. SUPABASE SETUP
# ============================================

echo "🗄️ Setting up Supabase..."
mkdir -p supabase
cd supabase

# Initialize Supabase
npx supabase init

# Migration for complete schema
cat > migrations/00001_initial_schema.sql << 'EOF'
-- Enable extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- See production-architecture artifact for complete schema
-- Copy schema from there

-- Initial seed data
INSERT INTO dimensions (name, weight) VALUES
  ('values', 1.5),
  ('work_style', 1.3),
  ('relationships', 1.4),
  ('learning', 1.2),
  ('decision_making', 1.4),
  ('time_management', 1.1),
  ('creativity', 1.0),
  ('risk_tolerance', 1.3),
  ('communication', 1.2),
  ('environment', 1.0),
  ('mental_state', 1.1),
  ('financial', 1.2),
  ('social', 1.1),
  ('health', 1.2),
  ('purpose', 1.3);

-- Function to update updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Apply to tables
CREATE TRIGGER update_profiles_updated_at BEFORE UPDATE ON profiles
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
EOF

cd ..

# ============================================
# 5. DEPLOYMENT SCRIPTS
# ============================================

echo "📦 Creating deployment scripts..."
mkdir -p scripts

# Deploy to Vercel
cat > scripts/deploy-vercel.sh << 'EOF'
#!/bin/bash

echo "🚀 Deploying to Vercel..."

# Install Vercel CLI if not present
if ! command -v vercel &> /dev/null; then
    npm i -g vercel
fi

# Deploy web app
cd apps/web

# Production deployment
vercel --prod

cd ../..

echo "✅ Vercel deployment complete!"
EOF

chmod +x scripts/deploy-vercel.sh

# Deploy training service to Railway
cat > scripts/deploy-training.sh << 'EOF'
#!/bin/bash

echo "🚂 Deploying to Railway..."

cd services/training

# Install Railway CLI if not present
if ! command -v railway &> /dev/null; then
    npm i -g @railway/cli
fi

# Login to Railway
railway login

# Link to project (first time)
# railway link

# Deploy
railway up

cd ../..

echo "✅ Railway deployment complete!"
EOF

chmod +x scripts/deploy-training.sh

# Complete deployment script
cat > scripts/deploy.sh << 'EOF'
#!/bin/bash

set -e  # Exit on error

echo "🚀 Starting complete deployment..."

# 1. Run tests
echo "🧪 Running tests..."
pnpm test

# 2. Build all packages
echo "📦 Building packages..."
pnpm build

# 3. Run Supabase migrations
echo "🗄️ Applying database migrations..."
cd supabase
npx supabase db push
cd ..

# 4. Deploy web app to Vercel
echo "🌐 Deploying web app..."
./scripts/deploy-vercel.sh

# 5. Deploy training service to Railway
echo "🤖 Deploying training service..."
./scripts/deploy-training.sh

echo "✅ Deployment complete!"
echo ""
echo "📊 Check status:"
echo "  Web: https://your-domain.vercel.app"
echo "  API: https://your-training-service.railway.app"
echo "  DB: https://app.supabase.com/project/your-project"
EOF

chmod +x scripts/deploy.sh

# Monitoring setup script
cat > scripts/setup-monitoring.sh << 'EOF'
#!/bin/bash

echo "📊 Setting up monitoring..."

# 1. Sentry
echo "Setting up Sentry..."
read -p "Enter Sentry DSN: " SENTRY_DSN
echo "NEXT_PUBLIC_SENTRY_DSN=$SENTRY_DSN" >> apps/web/.env.local

# 2. PostHog
echo "Setting up PostHog..."
read -p "Enter PostHog API Key: " POSTHOG_KEY
echo "NEXT_PUBLIC_POSTHOG_KEY=$POSTHOG_KEY" >> apps/web/.env.local

# 3. BetterUptime
echo "Setting up BetterUptime..."
echo "Add your URLs at: https://betteruptime.com"

echo "✅ Monitoring setup complete!"
EOF

chmod +x scripts/setup-monitoring.sh

# ============================================
# 6. CI/CD CONFIGURATION
# ============================================

echo "⚙️ Setting up CI/CD..."
mkdir -p .github/workflows

cat > .github/workflows/ci.yml << 'EOF'
name: CI

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main, develop]

jobs:
  test:
    runs-on: ubuntu-latest
    
    steps:
      - uses: actions/checkout@v3
      
      - name: Setup Node.js
        uses: actions/setup-node@v3
        with:
          node-version: '20'
          
      - name: Setup pnpm
        uses: pnpm/action-setup@v2
        with:
          version: 8
      
      - name: Install dependencies
        run: pnpm install
      
      - name: Run tests
        run: pnpm test
      
      - name: Type check
        run: pnpm type-check
      
      - name: Lint
        run: pnpm lint
      
      - name: Build
        run: pnpm build

  deploy:
    needs: test
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    
    steps:
      - uses: actions/checkout@v3
      
      - name: Deploy to Vercel
        uses: amondnet/vercel-action@v25
        with:
          vercel-token: ${{ secrets.VERCEL_TOKEN }}
          vercel-org-id: ${{ secrets.VERCEL_ORG_ID }}
          vercel-project-id: ${{ secrets.VERCEL_PROJECT_ID }}
          vercel-args: '--prod'
      
      - name: Deploy to Railway
        run: |
          npm i -g @railway/cli
          railway up
        env:
          RAILWAY_TOKEN: ${{ secrets.RAILWAY_TOKEN }}
EOF

# ============================================
# 7. DOCKER COMPOSE (LOCAL DEVELOPMENT)
# ============================================

cat > docker-compose.yml << 'EOF'
version: '3.8'

services:
  postgres:
    image: postgres:15
    environment:
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: digital_twin
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
  
  redis:
    image: redis:7
    ports:
      - "6379:6379"
  
  training-api:
    build: ./services/training
    ports:
      - "8000:8000"
    environment:
      DATABASE_URL: postgresql://postgres:postgres@postgres:5432/digital_twin
    depends_on:
      - postgres
      - redis
    volumes:
      - ./services/training:/app
      - models:/models

volumes:
  postgres_data:
  models:
EOF

# ============================================
# 8. MAKEFILE (CONVENIENT COMMANDS)
# ============================================

cat > Makefile << 'EOF'
.PHONY: install dev build test deploy clean

install:
	pnpm install
	cd services/training && pip install -r requirements.txt

dev:
	docker-compose up -d
	pnpm dev

build:
	pnpm build

test:
	pnpm test

deploy:
	./scripts/deploy.sh

clean:
	rm -rf node_modules
	rm -rf apps/*/node_modules
	rm -rf packages/*/node_modules
	rm -rf apps/*/.next
	docker-compose down -v

setup:
	./setup.sh
	./scripts/setup-monitoring.sh

db-migrate:
	cd supabase && npx supabase db push

db-reset:
	cd supabase && npx supabase db reset
EOF

# ============================================
# 9. README
# ============================================

cat > README.md << 'EOF'
# Digital Twin System

Your personal AI that learns from your choices and makes decisions like you.

## Quick Start

```bash
# 1. Clone and setup
git clone https://github.com/yourusername/digital-twin
cd digital-twin
make setup

# 2. Configure environment
cp apps/web/.env.local.example apps/web/.env.local
cp services/training/.env.example services/training/.env
# Fill in your API keys

# 3. Start local development
make dev

# 4. Deploy to production
make deploy
```

## Architecture

- **Frontend**: Next.js 15 on Vercel
- **Backend**: FastAPI on Railway
- **Database**: Supabase (PostgreSQL)
- **Training**: Stable-Baselines3 + Ray
- **Monitoring**: Sentry + PostHog + BetterUptime

## Documentation

See `/docs` for detailed documentation.

## License

MIT
EOF

# ============================================
# FINAL MESSAGE
# ============================================

echo ""
echo "✅ Project setup complete!"
echo ""
echo "📁 Project structure created"
echo "⚙️ Configuration files generated"
echo "🚀 Deployment scripts ready"
echo ""
echo "Next steps:"
echo "1. cd digital-twin"
echo "2. Fill in .env files with your API keys"
echo "3. Run 'make dev' to start development"
echo "4. Run 'make deploy' when ready to deploy"
echo ""
echo "📖 Read README.md for detailed instructions"
echo ""