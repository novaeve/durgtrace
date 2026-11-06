"""Experiment-local AIMD concurrency and cooldown; never changes model payloads."""
from pathlib import Path
from contextlib import contextmanager
import json,threading,time
ROOT=Path(__file__).resolve().parent
class Gate:
 def __init__(self,initial=2,minimum=1,maximum=4):
  self.cv=threading.Condition();self.limit=initial;self.minimum=minimum;self.maximum=maximum;self.configured_maximum=maximum
  self.active=0;self.cooldown=0;self.last_throttle=time.time();self.last_growth=time.time()
  self.successes=0;self.strikes=0;self.total_throttles=0
 def state_locked(self):
  return {'limit':self.limit,'minimum':self.minimum,'maximum':self.maximum,'configured_maximum':self.configured_maximum,'active_requests':self.active,
          'cooldown_until':self.cooldown,'stable_successes':self.successes,
          'throttle_events':self.total_throttles,'time':time.time()}
 def write_locked(self):
  tmp=ROOT/'rate_state.tmp';tmp.write_text(json.dumps(self.state_locked(),indent=2));tmp.replace(ROOT/'rate_state.json')
 def snapshot(self):
  with self.cv:return self.state_locked()
 @contextmanager
 def acquire(self):
  with self.cv:
   while self.active>=self.limit or time.time()<self.cooldown:self.cv.wait(timeout=.5)
   self.active+=1;self.write_locked()
  try:yield
  finally:
   with self.cv:
    self.active-=1;self.write_locked();self.cv.notify_all()
 def throttle(self,retry_after=0):
  with self.cv:
   self.total_throttles+=1;self.strikes+=1;self.successes=0;self.last_throttle=time.time()
   self.limit=max(self.minimum,self.limit//2)
   delay=max(retry_after,min(120,10*2**min(self.strikes-1,4)))
   self.cooldown=max(self.cooldown,time.time()+delay)
   self.write_locked();self.cv.notify_all()
   return delay
 def success(self):
  with self.cv:
   self.successes+=1
   now=time.time()
   if self.successes>=24 and now-self.last_throttle>=60 and now-self.last_growth>=60:
    self.limit=min(self.maximum,self.limit+1);self.successes=0;self.strikes=0;self.last_growth=now
   self.write_locked();self.cv.notify_all()
 def capacity(self,slots):
  with self.cv:
   cap=max(self.minimum,min(self.configured_maximum,int(slots)));delta=cap-self.maximum
   self.maximum=cap;self.limit=min(self.limit,cap);now=time.time()
   if delta>0 and (self.total_throttles==0 or now-self.last_throttle>=60) and now>=self.cooldown:self.limit=min(cap,self.limit+delta)
   self.write_locked();self.cv.notify_all()
STATE=Gate(initial=16,maximum=16)

