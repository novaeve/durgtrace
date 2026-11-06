import remote
c=remote.connect();s=c.open_sftp();s.put(str(remote.ROOT/'test_slots.py'),'/yimin/zlc/molclaw_type4_20261003/test_slots.py');s.close()
remote.run(c,'cd /yimin/zlc/molclaw_type4_20261003 && /usr/bin/python3.10 test_slots.py')
c.close()
