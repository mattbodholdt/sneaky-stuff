## Tor Socks Proxy

Socks proxy fronting Tor that expires circuits an a timed interval.

Environment Overrides:
usage: ./torProxy.py
usage: python3 torProxy.py

Tor proxy that expires the group of circuits interval (to keep things frosty..).

optional arguments:
  -h, --help            show this help message and exit
  --torBinary TORBINARY, -tor TORBINARY
                        Path to tor binary, default is the value of TOR_BINARY_PATH if populated, fallback uses shutil.which('tor') to locate the path. Your default: /opt/homebrew/bin/tor
  --bindAddress BINDADDRESS, -a BINDADDRESS
                        Address for the proxy to bind to. Usually 0.0.0.0 or 127.0.0.1. Default is the value of BIND_ADDRESS or 127.0.0.1
  --socksPort SOCKSPORT, -p SOCKSPORT
                        Port for the proxy to bind to, default is the value of SOCKS_PORT or 9050
  --controlPort CONTROLPORT, -c CONTROLPORT
                        Port for the proxy controller to bind to, default is the value of CONTROL_PORT or 9051
  --ipLifetime IPLIFETIME, -i IPLIFETIME
                        Duration in seconds before a new NEWNY signal is sent, rotating the circuits. Default is 3600
  --outputCircuitIP OUTPUTCIRCUITIP, -o OUTPUTCIRCUITIP
                        Whether or not to output the circuit ip to stdout when it changes (uses requests library). Default is the value of OUTPUT_EXIT_IP or True
  --caBundle REQUESTS_CA_BUNDLE, -ca REQUESTS_CA_BUNDLE
                        CA Bundle to use if check is enabled and using https. If not provided the value of REQUESTS_CA_BUNDLE will be used. Otherwise, common (Linux) locations are searched and the first match is used.
  --exitNodeLocales EXITNODELOCALES, -en EXITNODELOCALES
                        Comma seperated list of countries to exit from, see https://en.wikipedia.org/wiki/ISO_3166-1_alpha-2#O. Default is {ar},{is},{ru},{ma},{mm},{ua}

Expiring circuits: The NEWNY signal triggers a switch over to new circuits; therefore, new requests will not share any circuits which were previously active. It also clears the DNS cache


## Avoid Leaky DNS... 
(Mixed mileage here...)

## use proxychains and tor-resolve
```sh
proxychains4 nmap -sT -PN -n -sV --script ssl-enum-ciphers -p 443 $(tor-resolve -5 start.duckduckgo.com localhost:9050)
```

to debug that:
```sh
sh -xc "proxychains4 nmap -sT -PN -n -sV --script ssl-enum-ciphers -p 443 $(tor-resolve -5 start.duckduckgo.com localhost:9050)"
```

## curl (version new enough to have the socks5 options)
```sh
curl -LSs --socks5-hostname localhost:9050 'https://api.ipify.org/?format=text'
```

### tor-resolve to do DNS lookups
tor-resolve -v -5 api.ipify.org localhost:9050


## validate circuit rotation, curl on a loop..
Remember to shorten the lifetime duration (--ipLifetime IPLIFETIME, -i IPLIFETIME) param when testing..  And/or wait long enough.

```sh
loop=true; while [ $loop == true ]; do printf "$(curl -LSs --socks5 127.0.0.1:9050 'https://api.ipify.org/?format=text')\n\n"; sleep 30; done
```
Or if you want to use a hostname, use the --socks5-hostname switch.
```sh
loop="true"; while [ "$loop" == "true" ]; do printf "$(curl -LSs --socks5-hostname localhost:9050 'https://api.ipify.org/?format=text')\n\n"; sleep 30; done
```

## Kill it
If it does get stuck somehow, the script does attempt to kill anything conflicting.

This likely will work:
```sh
kill -9 $(ps | grep $(command -v tor) | grep -v grep | awk '{ print $1 }')
```
