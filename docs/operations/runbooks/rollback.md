# Rollback Runbook

## 1. Symptoms
- The newly deployed version of Atrium is throwing 5xx errors or failing to spawn sandbox pods.
- API latency is unacceptably high post-deploy.

## 2. Diagnosis
- Check logs: `kubectl logs -l app=atrium-api -n atrium-system`
- Check Prometheus metrics for 5xx rates and sandbox creation failures.

## 3. Resolution
1. **Application Rollback:**
   ```bash
   helm rollback atrium 0 -n atrium-system
   ```
2. **Database Rollback:**
   Atrium uses forward-only migrations. To roll back a database migration, you must restore the database from the pre-deployment snapshot.
   - If using RDS, restore the snapshot created immediately before the deployment.

## 4. Prevention
- Ensure staging environment matches production closely.
- Improve test coverage for the specific failure mode encountered.
