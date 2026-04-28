# Deploy Runbook

## 1. Symptoms
- Need to roll out a new version of the Atrium API or Webhook Worker.

## 2. Pre-flight Checks
1. Ensure the new Docker image (`atrium-api:tag`) is built and pushed to the registry.
2. Verify that any required database migrations have succeeded.
3. Check `values.yaml` for correct tags and secret names.

## 3. Resolution (Deploy Command)
```bash
helm upgrade --install atrium ./deploy/helm/atrium -n atrium-system -f ./deploy/helm/atrium/values.yaml
```

## 4. Post-deploy Verification
- Verify the API pods are running: `kubectl get pods -n atrium-system`
- Verify the health endpoint returns 200: `curl -fsS https://atrium.example.com/api/v1/health`
- Run a synthetic session test to ensure sandbox provisioning works.

## 5. Prevention
- Ensure CI pipeline runs unit and integration tests before allowing a deployment.
