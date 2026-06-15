from enum import Enum


class StreamingHealth(str, Enum):
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    STALLED = "STALLED"
    DISCONNECTED = "DISCONNECTED"
    ERROR = "ERROR"


class _ConnectionListener:
    def __init__(self, owner):
        self.owner = owner

    def onStatusChange(self, status):
        self.owner.status = (
            StreamingHealth.CONNECTED if status.startswith("CONNECTED")
            else StreamingHealth.STALLED if "STALLED" in status
            else StreamingHealth.CONNECTING if status.startswith("CONNECTING")
            else StreamingHealth.DISCONNECTED
        )

    def onServerError(self, _code, _message):
        self.owner.status = StreamingHealth.ERROR


class IGStreamingClient:
    def __init__(self, config, session):
        if config.streaming_mode == "MARKET":
            raise ValueError("MARKET subscription is deprecated; use PRICE or CHART_TICK")
        if not session.lightstreamer_endpoint:
            raise ValueError("IG session did not provide a Lightstreamer endpoint")
        self.config, self.session = config, session
        self.status, self.client, self.subscriptions = StreamingHealth.DISCONNECTED, None, []

    @staticmethod
    def _library():
        try:
            from lightstreamer.client import LightstreamerClient, Subscription
        except ImportError as exc:
            raise RuntimeError("Install lightstreamer-client-lib to use IG streaming") from exc
        return LightstreamerClient, Subscription

    def connect(self):
        LightstreamerClient, _ = self._library()
        self.client = LightstreamerClient(self.session.lightstreamer_endpoint, None)
        self.client.connectionDetails.setUser(self.session.account_id)
        self.client.connectionDetails.setPassword(
            f"CST-{self.session.cst}|XST-{self.session.security_token}"
        )
        self.client.addListener(_ConnectionListener(self))
        self.status = StreamingHealth.CONNECTING
        self.client.connect()

    def subscribe_price(self, epic: str, listener):
        _, Subscription = self._library()
        subscription = Subscription(
            "MERGE", [f"PRICE:{self.session.account_id}:{epic}"],
            list(self.config.stream_price_fields),
        )
        subscription.setDataAdapter("Pricing")
        subscription.addListener(listener)
        self.client.subscribe(subscription)
        self.subscriptions.append(subscription)
        return subscription

    def subscribe_chart_ticks(self, epic: str, listener):
        _, Subscription = self._library()
        subscription = Subscription(
            "DISTINCT", [f"CHART:{epic}:TICK"], list(self.config.stream_chart_tick_fields)
        )
        subscription.addListener(listener)
        self.client.subscribe(subscription)
        self.subscriptions.append(subscription)
        return subscription

    def subscribe_trade_updates(self, listener):
        _, Subscription = self._library()
        subscription = Subscription(
            "DISTINCT", [f"TRADE:{self.session.account_id}"], ["CONFIRMS", "OPU", "WOU"]
        )
        subscription.addListener(listener)
        self.client.subscribe(subscription)
        self.subscriptions.append(subscription)
        return subscription

    def disconnect(self):
        if self.client:
            self.client.disconnect()
        self.status = StreamingHealth.DISCONNECTED
