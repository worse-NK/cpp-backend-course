#!/usr/bin/env python3
"""Bounded, localhost-only RabbitMQ management HTTP helper, not an AMQP client.

No delete endpoint, queue purge or arbitrary URL is accepted. The requeue action
uses management basic.get and is deliberately not an AMQP crash/confirm test.
"""
import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.request

BASE = 'http://127.0.0.1:25673/api/'
VHOST = 'course11'
EXCHANGE = 'course11.events'
QUEUE = 'course11.audit'


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('Redirects are not allowed in this localhost-only helper')


def request(method, path, body=None):
    password = os.environ.get('COURSE11_RABBIT_PASSWORD', '')
    if not password:
        raise ValueError('Set COURSE11_RABBIT_PASSWORD; do not pass it on the command line')
    token = base64.b64encode(('course11:' + password).encode()).decode()
    headers = {'Authorization': 'Basic ' + token, 'Content-Type': 'application/json'}
    payload = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(BASE + path, data=payload, headers=headers, method=method)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    with opener.open(req, timeout=5) as response:
        data = response.read(65537)
    if len(data) > 65536:
        raise ValueError('Unexpectedly large management response')
    return json.loads(data) if data else None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('setup', 'publish', 'peek', 'take', 'status'))
    action = parser.parse_args(argv).action
    if action == 'setup':
        request('PUT', f'exchanges/{VHOST}/{EXCHANGE}',
                {'type': 'direct', 'durable': True, 'auto_delete': False, 'arguments': {}})
        request('PUT', f'queues/{VHOST}/{QUEUE}',
                {'durable': True, 'auto_delete': False,
                 'arguments': {'x-queue-type': 'quorum'}})
        result = request('POST', f'bindings/{VHOST}/e/{EXCHANGE}/q/{QUEUE}',
                         {'routing_key': 'orders.created', 'arguments': {}})
    elif action == 'publish':
        result = request('POST', f'exchanges/{VHOST}/{EXCHANGE}/publish',
                         {'routing_key': 'orders.created', 'payload': 'evt-101|order=101',
                          'payload_encoding': 'string',
                          'properties': {'delivery_mode': 2, 'message_id': 'evt-101'}})
        if result != {'routed': True}:
            raise ValueError('Message was not routed to a queue')
    elif action in ('peek', 'take'):
        result = request('POST', f'queues/{VHOST}/{QUEUE}/get',
                         {'count': 1, 'ackmode': 'ack_requeue_true' if action == 'peek'
                          else 'ack_requeue_false', 'encoding': 'auto', 'truncate': 4096})
    else:
        result = request('GET', f'queues/{VHOST}/{QUEUE}')
        result = {k: result.get(k) for k in ('name', 'type', 'messages_ready', 'messages_unacknowledged')}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, urllib.error.URLError) as error:
        print('Local lab request failed: ' + str(error), file=sys.stderr)
        sys.exit(1)
