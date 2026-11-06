from provider import Relay as BaseRelay,MODEL
class Relay(BaseRelay):
    def complete(self,messages,label,max_tokens=None):
        return super().complete(messages,label,max_tokens=max_tokens)