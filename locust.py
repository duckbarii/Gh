from locust import HttpUser, task, between

class TestUser(HttpUser):
    wait_time = between(0, 5)

    @task
    def index(self):
        self.client.get("/")
        