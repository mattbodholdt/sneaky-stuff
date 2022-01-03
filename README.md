# sneaky-stuff

torPorxy.py:

Python script to establish a tor connection, then expire the established circuits every five minutes (by default) so further connections source from different IPs.

```sh
python3 /etc/tor/torProxy.py
```

or 
```sh
./torPorxy.py
```

For usage/additional parameters:
```sh
./torProxy.py -h
```
