class BadConfig:
    NAMES = ["admin", "root"]
    SERVICE_OFFERS = ["free", "premium"]

    def __init__(self):
        self.names = []
        self.service_offers = []
