# Agent 53 - Airbnb Sniper
# Finds good deals (desperate landlords / undervalued properties)

class Agent53Sniper:
    def __init__(self):
        self.name = "Agent 53 - Sniper"
        print(f"{self.name} is ready")

    def find_deals(self):
        print("Looking for good Airbnb deals...")
        # TODO: call scrapers later
        return []

if __name__ == "__main__":
    agent = Agent53Sniper()
    agent.find_deals()
