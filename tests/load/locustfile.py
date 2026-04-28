from locust import HttpUser, task, between
import secrets

class AtriumUser(HttpUser):
    wait_time = between(1, 5)
    host = "http://localhost:8080"
    
    def on_start(self):
        # We need an admin workspace to hit the endpoints, but for load testing
        # we'll assume the API has auth mocked or we pass a known static key via env
        self.client.headers.update({"Authorization": "Bearer load-test-key"})
        self.workspace_id = f"ws_{secrets.token_hex(4)}"

    @task(3)
    def create_thread(self):
        self.client.post("/api/v1/threads", json={"title": "Load Test Thread"})

    @task(1)
    def create_session(self):
        # Start a synthetic session that just says hello
        res = self.client.post("/api/v1/sessions", json={
            "objective": "Say hello to the load tester",
            "model": "anthropic:claude-sonnet-4-6"
        })
        if res.status_code == 201:
            session_id = res.json()["session_id"]
            self.client.get(f"/api/v1/sessions/{session_id}/stream", stream=True, timeout=10)

    @task(5)
    def list_threads(self):
        self.client.get("/api/v1/threads")

    @task(2)
    def check_health(self):
        self.client.get("/api/v1/health")
