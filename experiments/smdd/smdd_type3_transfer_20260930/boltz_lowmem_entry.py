"""Process-local diagnostics and allocator tuning; no model/metric changes."""
import traceback
import torch
from boltz.model.models.boltz2 import Boltz2
original=Boltz2.forward

def forward(self,*a,**kw):
 try:return original(self,*a,**kw)
 except torch.cuda.OutOfMemoryError:
  print('EXACT_OOM_TRACE',flush=True);traceback.print_exc()
  print(torch.cuda.memory_summary(),flush=True)
  raise
Boltz2.forward=forward
from boltz.main import cli
cli()
