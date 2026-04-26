class BaseAgent:
    """
    BaseAgent defines the contract for all agents.
    All agents must inherit and implement run().
    """

    def __init__(self, agent_type: str):
        self.agent_type = agent_type
        self.status = "CREATED"

    async def run(self, input_data: dict) -> dict:
        """
        Execute agent logic.
        Must be overridden by child classes.
        """
        raise NotImplementedError("Agent must implement run() method")

    def set_status(self, status: str):
        self.status = status

    def get_status(self) -> str:
        return self.status
