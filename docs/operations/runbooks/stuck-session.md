# Stuck Session Runbook

## 1. Symptoms
- A session remains in the `RUNNING` state for > 1 hour with no recent events or progress.
- Users report that their agent session has frozen.

## 2. Diagnosis
- Query `last_active_at` in the `sessions` table.
- Identify the sandbox pod associated with the session:
  ```bash
  kubectl get pods -n atrium-sandbox -l session-id=<SESSION_ID>
  ```
- Describe the pod: `kubectl describe pod <pod-name> -n atrium-sandbox`
- Check pod logs: `kubectl logs <pod-name> -n atrium-sandbox`

## 3. Resolution
There are two ways to forcefully terminate a stuck session:
1. **Via API (Preferred):**
   ```bash
   curl -X POST https://atrium.example.com/api/v1/sessions/<SESSION_ID>/cancel -H "Authorization: Bearer <ADMIN_KEY>"
   ```
2. **Via Kubernetes:**
   ```bash
   kubectl delete pod <pod-name> -n atrium-sandbox
   ```
   *(The orchestrator's watchdog will mark the session as `FAILED` on the next tick).*

## 4. Prevention
- Ensure the `timeout_seconds` in `HarnessAgent` and the `active_deadline_seconds` in `KubernetesSandboxRunner` are correctly aligned.
- Improve inner runtime error handling to exit cleanly on timeouts.
