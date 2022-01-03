#!/usr/bin/env python3

import argparse
import functools
import json
import logging
import os
import shutil
import signal
import sys
from time import sleep

import requests
from stem import Signal, StreamStatus, process
from stem.control import Controller, EventType
from stem.util.connection import get_connections, system_resolvers
from stem.util.system import pid_by_name


class BandwidthReporter(object):
    def __init__(self, controller):
        self.controller = controller

    def output_bandwidth(self):
        bytes_read = self.controller.get_info("traffic/read")
        bytes_written = self.controller.get_info("traffic/written")
        return {'bytesRead': bytes_read, 'bytesWritten': bytes_written}


def configureLogging():
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        format='%(asctime)s:%(levelname)s:%(message)s', level=log_level)
    logging.debug("Log Level: " + str(logging.getLogger().getEffectiveLevel()
                                      ) + ".  To override, set LOG_LEVEL environment variable.")
    return logging.getLogger()


def findCABundle(logger):
    ca_bundle = os.getenv('CA_BUNDLE', None)
    if ca_bundle is not None:
        return ca_bundle
    # search common locations, use first hit
    common_locations = [
        '/etc/ssl/certs/ca-certificates.crt',
        '/etc/ssl/cert.pem',
        '/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem',
        '/etc/pki/tls/certs/ca-bundle.crt',
        '/etc/ssl/ca-bundle.pem',
        '/usr/local/etc/ssl/cert.pem'
    ]
    for file in common_locations:
        logger.debug("findCABundle: Checking " + file)
        if os.path.exists(file):
            logger.debug(file + " found!")
            return file
    if ca_bundle is None:
        logger.error("No CA bundle found, cert validation will fail!")
        return None


def outputExitNodeInfo(cntrl, logger, cEvent):
    out = []
    if cEvent is not None:
        circs = cntrl.get_circuit(cEvent.circ_id)
    else:
        circs = cntrl.get_circuits()
    logger.debug("Circuits: " + str(len(circs)))
    for c in circs:
        logger.debug(str(c))
        try:
            exit_fingerprint = c.path[-1][0]
            exit_relay = cntrl.get_network_status(exit_fingerprint)
            locale = cntrl.get_info("ip-to-country/%s" %
                                    exit_relay.address, 'unknown')
            pid = cntrl.get_pid()
        except Exception as e:
            logger.error("Exception: " + str(e))
            out.append({'error': str(e)})
        else:
            out.append({
                "address": exit_relay.address + ":" + str(exit_relay.or_port),
                "fingerprint": exit_relay.fingerprint,
                "nickname": exit_relay.nickname,
                "locale": locale,
                "pid": pid
            }
            )
    logger.info("All Circuits: " + json.dumps(out))


def switchIP(swController, logger, outputCircuitIP, headers, proxies):
    swController.authenticate()
    stream_listener = functools.partial(stream_event, swController)
    swController.add_event_listener(stream_listener, EventType.STREAM)
    if swController.is_newnym_available():
        event = swController.signal(Signal.NEWNYM)
        outputExitNodeInfo(cntrl=swController, cEvent=event, logger=logger)
    else:
        wait_time = swController.get_newnym_wait()
        logger.info("newnym not available for another " +
                    str(wait_time) + " seconds..  Hanging tight!")
        sleep(int(wait_time) + 1)
        if swController.is_newnym_available():
            event = swController.signal(Signal.NEWNYM)
            outputExitNodeInfo(cntrl=swController, cEvent=event, logger=logger)
            if outputCircuitIP:
                requestsOutputIP(
                    request_headers=headers,
                    request_proxies=proxies,
                    logger=logger)


def stream_event(controller, event):
    pid = controller.get_pid()
    if event.status == StreamStatus.SUCCEEDED and event.circ_id:
        circ = controller.get_circuit(event.circ_id)
        exit_fingerprint = circ.path[-1][0]
        exit_relay = controller.get_network_status(exit_fingerprint)

        streamInfo = {
            "target": event.target,
            "pid": pid,
            "circuit_id": event.circ_id,
            "connect": exit_relay.address + ":" + str(exit_relay.or_port),
            "fingerprint": exit_relay.fingerprint,
            "nickname": exit_relay.nickname,
            "locale": controller.get_info("ip-to-country/%s" % exit_relay.address),
            "raw_event": str(event)
        }
        logging.debug(json.dumps(streamInfo))

    else:
        otherEvent = {
            "target": event.target,
            "pid": pid,
            "raw_event": str(event)
        }
        logging.debug(json.dumps(otherEvent))


def requestsOutputIP(request_headers, request_proxies, logger, scheme='https', host='api.ipify.org', uri='/?format=json'):
    url = scheme + '://' + host + uri
    exitIP = requests.get(url, headers=request_headers,
                          proxies=request_proxies).text
    logger.info(
        "Exit node ip, obtained by the requests module via the proxy: " + str(exitIP))


def runTor(args, tor_path):
    return process.launch_tor_with_config(
        config={
            'ControlPort': str(args.controlPort),
            'SocksPort': str(args.socksPort),
            'ExitNodes': str(args.exitNodeLocales),
            'Log': [
                'NOTICE stdout',
                'ERR stderr',
            ],
        },
        timeout=90,
        completion_percent=100,
        tor_cmd=tor_path,
        take_ownership=True
    )


def killTor(procName, logger):
    pids = pid_by_name('tor', multiple=True)
    logger.debug("pids " + str(pids) + " to kill, count " + str(len(pids)))
    # kill the processes that matched
    if len(pids) > 0:
        for p in pids:
            try:
                os.kill(p, signal.SIGKILL)
            except OSError:
                logger.debug("Failed to kill process: " +
                             str(procName) + ", " + str(p))
            else:
                logger.info("Killed process: " +
                            str(procName) + ", " + str(p))


def parseArgs():
    parser = argparse.ArgumentParser(description='Tor proxy that expires the group of circuits interval (to keep things frosty..).',
                                     usage="./%(prog)s\nusage: python3 %(prog)s",
                                     epilog="Expiring circuits: The NEWNY signal triggers a switch over to new circuits; therefore, \
                                             new requests will not share any circuits which were previously active.  It also clears the DNS cache.")
    parser.add_argument("--torBinary", "-tor", required=False, type=str, default=os.getenv('TOR_BINARY_PATH', shutil.which('tor')),
                        help="Path to tor binary, default is the value of TOR_BINARY_PATH if populated, fallback uses shutil.which('tor') to locate the path. Your default: %(default)s")
    parser.add_argument("--bindAddress", "-a", required=False, type=str, default=os.getenv('BIND_ADDRESS', "127.0.0.1"),
                        help="Address for the proxy to bind to.  Usually 0.0.0.0 or 127.0.0.1.  Default is the value of BIND_ADDRESS or %(default)s")
    parser.add_argument("--socksPort", "-p", required=False, type=int, default=int(os.getenv('SOCKS_PORT', "9050")),
                        help="Port for the proxy to bind to, default is the value of SOCKS_PORT or %(default)s")
    parser.add_argument("--controlPort", "-c", required=False, type=int, default=int(os.getenv('CONTROL_PORT', "9051")),
                        help="Port for the proxy controller to bind to, default is the value of CONTROL_PORT or %(default)s")
    parser.add_argument("--ipLifetime", "-i", required=False, type=int, default=int(os.getenv('IP_LIFE_SECONDS', "3600")),
                        help="Duration in seconds before a new NEWNY signal is sent, rotating the circuits.  Default is %(default)s"),
    parser.add_argument("--outputCircuitIP", "-o", required=False, type=bool, default=bool(os.getenv('OUTPUT_EXIT_IP', "True")),
                        help="Whether or not to output the circuit ip to stdout when it changes (uses requests library).  Default is the value of OUTPUT_EXIT_IP or %(default)s"),
    parser.add_argument("--caBundle", "-ca", action="store", dest='REQUESTS_CA_BUNDLE', required=False, type=str, default=os.getenv('REQUESTS_CA_BUNDLE', findCABundle(logger=logging.getLogger())),
                        help="CA Bundle to use if check is enabled and using https.  If not provided the value of REQUESTS_CA_BUNDLE will be used.  Otherwise, common (Linux) locations are searched and the first match is used.")
    parser.add_argument("--exitNodeLocales", "-en", required=False, type=str,
                        default=str(os.getenv('EXIT_NODES_LOCALES',
                                    '{ar},{is},{ru},{ma},{mm},{ua}')),
                        help='Comma seperated list of countries to exit from, \
                                see https://en.wikipedia.org/wiki/ISO_3166-1_alpha-2#O. Default is %(default)s')
    return parser.parse_args()


def main(args, logger):

    global REQUESTS_CA_BUNDLE
    REQUESTS_CA_BUNDLE = args.REQUESTS_CA_BUNDLE

    logger.debug("REQUESTS_CA_BUNDLE: " + REQUESTS_CA_BUNDLE)

    # if args.outputCircuitIP is False, the items below do not need to be set as requests will not be used
    if bool(args.outputCircuitIP):
        requests_ua = os.getenv(
            'USER_AGENT_STRING', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36')
        headers = {'User-Agent': requests_ua}
        proxies = {
            'http': 'socks5://' + str(args.bindAddress) + ':9050',
            'https': 'socks5://' + str(args.bindAddress) + ':9050'
        }

    try:
        runTor(args=args, tor_path=args.torBinary)
    except OSError as e:
        logger.error("Failed to launch tor: " + str(e) +
                     " Attempting to kill any running tor processes and retry")

        try:
            killTor(procName="tor", logger=logger)
            runTor(args=args, tor_path=args.torBinary)
        except OSError as e2:
            logger.error("Failed to launch tor again: " + str(e2) + " Exiting")
            sys.exit(1)
        else:
            logger.info(
                "Successfully launched tor after killing running processes")

    # https://stem.torproject.org/api/control.html
    with Controller.from_port(port=int(args.controlPort), address=args.bindAddress) as controller:
        controller.authenticate()
        reporter = BandwidthReporter(controller)

        resolvers = system_resolvers()
        if not resolvers:
            logger.error(
                "Stem doesn't support any connection resolvers on this platform.")
            # sys.exit(1)
        logger.info(str(resolvers))
        picked_resolver = resolvers[0]  # lets just opt for the first
        logger.info("Connection resolution supported via: %s (picked %s)" % (
            ', '.join(resolvers), picked_resolver))

        tor_pids = pid_by_name('tor', multiple=True)
        logger.info("tor_pids: " + str(tor_pids))
        if not tor_pids:
            logger.error("Unable to get tor's pid. Is it running?")
            # sys.exit(1)
        elif len(tor_pids) > 1:
            logger.infos("You're running %i instances of tor, picking the one with pid %i" % (
                len(tor_pids), tor_pids[0]))
        else:
            logger.info("Tor is running with pid %s" % str(tor_pids))

        switchIP(swController=controller, logger=logger, outputCircuitIP=args.outputCircuitIP,
                 headers=headers, proxies=proxies)
        logger.info("Connections:")
        for conn in get_connections(picked_resolver, process_name='tor'):
            logger.info("  %s:%s => %s:%s" % (conn.local_address,
                        conn.local_port, conn.remote_address, conn.remote_port))

        # perma-loop!
        counter = 0
        loop = True
        while loop is True:
            counter += 1
            logger.info("Loop %i, sleeping %i seconds before attempting NEWNYM signal" % (
                counter, int(args.ipLifetime)))
            sleep(int(args.ipLifetime))
            logger.info("Connections:")
            for conn in get_connections(picked_resolver, process_name='tor'):
                logger.info("  %s:%s => %s:%s" % (
                    conn.local_address, conn.local_port, conn.remote_address, conn.remote_port))
            logger.info("Switching IPs for fun (or profit?).. Iteration " + str(counter) + "\n" +
                        "Bandwidth Stats: " + str(reporter.output_bandwidth()) + "\n" +
                        "Effective Rate Stats: " + str(controller.get_effective_rate()) + "\n" +
                        "Uptime: " + str(controller.get_uptime()))

            switchIP(swController=controller, logger=logger, outputCircuitIP=args.outputCircuitIP,
                     headers=headers, proxies=proxies)


if __name__ == '__main__':
    main(args=parseArgs(), logger=configureLogging())
