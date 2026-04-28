# Backfill Events Runbook

## 1. Symptoms
- The event store (Postgres) needs to be re-populated from the SQLite backup.
- A data-loss incident occurred, and events need to be replayed from a snapshot.

## 2. Diagnosis
- Identify the missing events or the date range of the data loss.
- Ensure the backup SQLite file `atrium_events.db` is accessible.

## 3. Resolution
1. Connect to the Atrium instance with access to the `atrium_events.db` file.
2. Run the backfill script (to be implemented as a CLI command or standalone script):
   ```bash
   python scripts/backfill_events.py --source atrium_events.db --target <POSTGRES_DSN>
   ```
3. Monitor the script output for any parsing errors or duplicates.

## 4. Prevention
- Ensure Postgres streaming replication and point-in-time recovery (PITR) are enabled.
- Validate backups automatically.
