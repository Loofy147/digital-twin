# Quick Start Guide - Deploy Your Digital Twin in 1 Day

## Overview

This guide will take you from zero to a deployed, working digital twin system in **8 hours**.

---

## Prerequisites (30 minutes)

### Accounts to Create
```bash
1. GitHub (free)          → https://github.com
2. Vercel (free)          → https://vercel.com
3. Supabase (free)        → https://supabase.com
4. Railway (free trial)   → https://railway.app
5. Cloudflare (free)      → https://cloudflare.com (optional)
```

### Local Setup
```bash
# Install Node.js 20+
https://nodejs.org

# Install pnpm
npm install -g pnpm

# Install Python 3.11+
https://python.org

# Install Git
https://git-scm.com
```

---

## Hour 1: Project Setup

### Step 1: Clone or Create Repository
```bash
# Option A: Use deployment script
curl -fsSL https://raw.githubusercontent.com/yourusername/digital-twin/main/setup.sh | bash

# Option B: Manual setup
git clone https://github.com/yourusername/digital-twin
cd digital-twin
chmod +x setup.sh
./setup.sh
```

### Step 2: Environment Configuration
```bash
# Copy environment templates
cp apps/web/.env.local.example apps/web/.env.local
cp services/training/.env.example services/training/.env

# You'll fill these in next steps
```

---

## Hour 2: Database Setup (Supabase)

### Step 1: Create Supabase Project
1. Go to https://supabase.com
2. Click "New Project"
3. Name: "digital-twin-prod"
4. Database Password: Generate strong password (save it!)
5. Region: Choose closest to you
6. Click "Create new project"

### Step 2: Get Connection Info
```bash
# In Supabase dashboard:
# Project Settings → API

# Copy these values:
NEXT_PUBLIC_SUPABASE_URL=https://xxxxx.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJhbG...
SUPABASE_SERVICE_ROLE_KEY=eyJhbG... (keep secret!)

# Paste into apps/web/.env.local
```

### Step 3: Run Migrations
```bash
cd digital-twin

# Link to your Supabase project
npx supabase link --project-ref your-project-ref

# Apply schema
npx supabase db push

# Verify
npx supabase db pull  # Should show tables
```

### Step 4: Seed Question Bank
```bash
# Generate 5000+ questions
cd apps/web
npm run generate-questions

# Import to database
npm run seed-questions
```

---

## Hour 3: Web App Deployment (Vercel)

### Step 1: Connect to Vercel
```bash
# Install Vercel CLI
npm i -g vercel

# Login
vercel login

# Link project
cd apps/web
vercel link
```

### Step 2: Set Environment Variables
```bash
# In Vercel dashboard or CLI:
vercel env add NEXT_PUBLIC_SUPABASE_URL
vercel env add NEXT_PUBLIC_SUPABASE_ANON_KEY
vercel env add SUPABASE_SERVICE_ROLE_KEY

# Paste the values from Supabase
```

### Step 3: Deploy
```bash
# Production deployment
vercel --prod

# You'll get a URL like:
# https://digital-twin-xxxxx.vercel.app
```

### Step 4: Custom Domain (Optional)
```bash
# In Vercel dashboard:
# Project → Settings → Domains
# Add your domain (e.g., mydigitaltwin.com)
# Update DNS records as instructed
```

---

## Hour 4: Training Service Deployment (Railway)

### Step 1: Create Railway Project
```bash
# Install Railway CLI
npm i -g @railway/cli

# Login
railway login

# Create project
cd services/training
railway init
```

### Step 2: Configure Environment
```bash
# In Railway dashboard:
# Add variables:

DATABASE_URL=postgresql://... (from Supabase)
SECRET_KEY=generate-random-key
MODEL_STORAGE_PATH=/models
```

### Step 3: Deploy
```bash
# Deploy to Railway
railway up

# Get URL
railway domain

# Should see: https://digital-twin-training.railway.app
```

### Step 4: Update Web App
```bash
# Add training API URL to Vercel
cd apps/web
vercel env add TRAINING_API_URL
# Enter: https://digital-twin-training.railway.app

# Redeploy
vercel --prod
```

---

## Hour 5: Testing & Verification

### Step 1: Test Web App
```bash
# Visit your Vercel URL
open https://digital-twin-xxxxx.vercel.app

# Should see:
# - Landing page
# - Sign up / Login
# - Question interface
```

### Step 2: Create Test Account
```bash
# Sign up with email
# Verify email (check inbox)
# Log in
```

### Step 3: Answer Questions
```bash
# Answer 10-20 questions
# Test different question types
# Try "Don't Care" option
# Check response time
```

### Step 4: Test Integrations
```bash
# Go to Settings → Integrations
# Connect Google Calendar (optional for now)
# Connect Contacts (optional for now)
# Verify sync works
```

---

## Hour 6: Monitoring Setup

### Step 1: Sentry (Error Tracking)
```bash
# Create account: https://sentry.io
# Create new project: "digital-twin-web"
# Copy DSN

# Add to Vercel
vercel env add NEXT_PUBLIC_SENTRY_DSN
# Paste DSN

# Redeploy
vercel --prod
```

### Step 2: PostHog (Analytics)
```bash
# Create account: https://posthog.com
# Get API key

# Add to Vercel
vercel env add NEXT_PUBLIC_POSTHOG_KEY
# Paste key

# Redeploy
vercel --prod
```

### Step 3: BetterUptime (Uptime Monitoring)
```bash
# Create account: https://betteruptime.com
# Add monitor:
  - URL: Your Vercel URL
  - Check frequency: 60 seconds
  - Regions: All
```

---

## Hour 7: First Training Run

### Step 1: Collect Responses
```bash
# Need at least 100 responses for first training
# Options:
# 1. Answer 100 questions yourself (1-2 hours)
# 2. Invite 10 friends, each answers 10 (faster)
# 3. Use synthetic data for testing (quickest)
```

### Step 2: Trigger Training
```bash
# Via API
curl -X POST https://your-training-api.railway.app/train \
  -H "Content-Type: application/json" \
  -d '{
    "profile_id": "your-user-id",
    "config": {
      "total_timesteps": 50000
    }
  }'

# Or via web UI:
# Settings → Training → "Start Training"
```

### Step 3: Monitor Training
```bash
# Check logs in Railway
railway logs

# Check status
curl https://your-training-api.railway.app/status/your-user-id

# Training takes 10-30 minutes for first run
```

### Step 4: Validate Results
```bash
# After training completes:
# Go to web app → Insights
# Should see:
  - Detected patterns
  - Learned preferences
  - Validation questions

# Answer validation questions
# Check accuracy score (target: 60%+ for first training)
```

---

## Hour 8: Polish & Launch Prep

### Step 1: Content Setup
```bash
# Add content to:
  - Landing page (apps/web/app/page.tsx)
  - About page
  - Privacy policy
  - Terms of service
  - Help documentation
```

### Step 2: Email Configuration
```bash
# Option A: Supabase Auth Emails (built-in)
# Configure in Supabase → Authentication → Email Templates

# Option B: Custom emails (Resend)
# Create account: https://resend.com
# Get API key
# Configure templates
```

### Step 3: Payment Setup (Optional)
```bash
# Stripe integration
# Create account: https://stripe.com
# Get API keys
# Add to Vercel env
vercel env add STRIPE_SECRET_KEY
vercel env add NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY
```

### Step 4: Final Checks
```bash
Checklist:
□ Web app loads fast (<2s)
□ Sign up/login works
□ Questions display correctly
□ Responses save properly
□ Integrations connect
□ Training completes
□ Monitoring active
□ Backups configured
□ SSL certificate valid
□ Mobile responsive
```

---

## Post-Deployment

### Week 1: Beta Testing
```bash
# Invite 10 beta users
# Collect feedback
# Fix critical bugs
# Iterate on UX
```

### Week 2-4: Optimization
```bash
# Performance tuning
# Database optimization
# Cost monitoring
# Feature additions
```

### Month 2-3: Growth
```bash
# Marketing launch
# Product Hunt
# Social media
# Content marketing
# First 100 users
```

---

## Troubleshooting

### Database Connection Issues
```bash
# Check Supabase status
https://status.supabase.com

# Verify connection string
psql $DATABASE_URL

# Check RLS policies
# Supabase → Authentication → Policies
```

### Vercel Deployment Fails
```bash
# Check build logs
vercel logs

# Common issues:
# - Missing environment variables
# - TypeScript errors
# - Dependencies not installed

# Force rebuild
vercel --force
```

### Training Service Issues
```bash
# Check Railway logs
railway logs

# Common issues:
# - Out of memory (upgrade plan)
# - Database timeout (check connection)
# - Missing dependencies (check requirements.txt)

# Restart service
railway restart
```

### Performance Issues
```bash
# Check metrics
# Vercel → Analytics
# Supabase → Database → Performance

# Common fixes:
# - Add database indexes
# - Enable caching
# - Optimize queries
# - Upgrade tiers
```

---

## Cost Summary (First Month)

```yaml
Free Tier (Recommended for Start):
  Vercel: $0 (Hobby)
  Supabase: $0 (Free tier)
  Railway: $5 (Trial)
  Domain: $12/year
  Total: $5-6/month

Paid Tier (When >100 users):
  Vercel Pro: $20/month
  Supabase Pro: $25/month
  Railway: $10/month
  Monitoring: $36/month
  Total: $91/month
```

---

## Next Steps

### Immediate (This Week)
1. Complete deployment (Hours 1-8)
2. Test thoroughly
3. Invite 5 beta users
4. Collect first responses

### Short Term (Month 1)
1. Gather feedback
2. Fix critical issues
3. Add mobile app
4. Train first real agents

### Medium Term (Months 2-3)
1. Public launch
2. Marketing campaign
3. First 100 users
4. Revenue generation

### Long Term (Year 1+)
1. Scale to 1000+ users
2. Advanced features
3. Team expansion
4. Platform business

---

## Resources

### Documentation
- Architecture: See `production-architecture` artifact
- Training: See `rl-implementation` artifact
- Integrations: See `integration-code-impl` artifact

### Support
- GitHub Issues: Your repository issues
- Community: Discord/Slack (create one)
- Email: support@your-domain.com

### Learning
- Supabase Docs: https://supabase.com/docs
- Vercel Docs: https://vercel.com/docs
- Next.js: https://nextjs.org/docs
- Stable-Baselines3: https://stable-baselines3.readthedocs.io

---

## Success Checklist

After following this guide, you should have:

✅ **Infrastructure**
- [ ] Web app deployed on Vercel
- [ ] Database on Supabase
- [ ] Training service on Railway
- [ ] Monitoring set up
- [ ] Domain configured

✅ **Features**
- [ ] User authentication
- [ ] Question interface
- [ ] Response collection
- [ ] Pattern detection
- [ ] Integration support
- [ ] Training pipeline

✅ **Operations**
- [ ] Automated backups
- [ ] Error tracking
- [ ] Analytics
- [ ] Uptime monitoring
- [ ] CI/CD pipeline

✅ **Documentation**
- [ ] README complete
- [ ] API documented
- [ ] User guide written
- [ ] Privacy policy
- [ ] Terms of service

**If you've checked all boxes, you're ready to launch! 🚀**

---

## Getting Help

Stuck? Check these artifacts:
1. `production-architecture` - Complete system design
2. `production-part2` - Training, security, scaling
3. `deployment-configs` - All config files and scripts
4. `master-roadmap` - 10-year detailed plan
5. This guide - Step-by-step deployment

**Everything is ready. Just execute the plan.**