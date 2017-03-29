#!/usr/bin/env python

import json
import logging
import argparse
import sys
import signal
import multiprocessing
import os

import requests

import drivers


def load_driver(path):
    """Load a python module."""
    if not path.endswith('.py'):
        path += '.py'
    if not os.path.isfile(path):
        raise ImportError('Path must be a file: %s', path)
    path = path.rstrip('.py')
    directory = os.path.dirname(path)
    if not directory in sys.path:
        sys.path.insert(0, directory)
    try:
        return __import__(os.path.basename(path), globals(), locals(), [], -1)
    except SyntaxError as exception:
        raise exception
    except ImportError as exception:
        print exception
        raise NotImplementedError("Unable to find requested module in path: %s" % (path))

def get_resume_id(elasticsearch_url, driver_name):
    query = {
        "query": {
            "match_all": {}
        },
        "sort": [
            { "timestamp":
                { "order": "desc" }
            },
        ],
        "size": 1
    }
    response = requests.get(elasticsearch_url + '/' + driver_name + '/_search', data=json.dumps(query))
    if not response.ok:
        logging.warning('No resume id found, starting from scratch.')
        return ''
    resume_id = json.loads(response.text)['hits']['hits'][0]['_id']
    logging.info('Found resume id: %s', resume_id)
    return resume_id


def main():

    if sys.version_info < (2,6) or sys.version_info > (2,8):
        raise SystemExit('Sorry, this code needs Python 2.6 or Python 2.7 (current: %s.%s)' % (sys.version_info[0], sys.version_info[1]))

    desc = 'Extracts data using the multiple drivers and posts data to elasticsearch.'
    parser = argparse.ArgumentParser(description=desc)

    parser.add_argument('-v', '--verbose', action='store_true', \
        help='Increase output verbosity')
    parser.add_argument('-e', '--elasticsearch', default='http://localhost:9200', \
        help='The Elasticsearch instance where the build info will be POSTed to.')
    parser.add_argument('-d', '--driver', required=True, help='The driver to use when parsing the URL.')
    parser.add_argument('-l', '--location', required=True, help='The URL to crawl for data.')
    parser.add_argument('-u', '--username', \
        help='The username for driver service authentication.')
    parser.add_argument('-p', '--password', \
        help='The password for driver service authentication.')

    args = parser.parse_args()

    logging.basicConfig(format='%(asctime)s::%(levelname)s::%(message)s')
    logging.getLogger().setLevel(getattr(logging, 'INFO'))

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logging.debug('Verbose mode activated.')

    # Sanity check
    if not args.elasticsearch.startswith('http'):
        raise SystemExit('The Elasticsearch instance must start with http')

    # Obtain the resume point (if there's already data on the destination)
    resume_id = get_resume_id(args.elasticsearch, args.driver)

    # Initialize the requested driver
    module_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'drivers', args.driver)
    driver = load_driver(module_path)

    # Prepare the elasticsearch client
    args.elasticsearch += '/' + args.driver + '/' + driver.get_type()

    def init_worker():
        signal.signal(signal.SIGINT, signal.SIG_IGN)
    pool = multiprocessing.Pool(initializer=init_worker)

    try:
        count = 0
        for task_results in pool.imap_unordered(driver.process_task, driver.get_tasks(args.location, args.username, args.password, resume_id)):
            # Post the results to the elastic search instance
            if isinstance(task_results, list):
                for result in task_results:
                    # The ID field is meant to avoid duplicates
                    url = args.elasticsearch
                    if 'id' in result.keys():
                        url += '/' + result['id']
                    requests.post(url, data=json.dumps(result))
            elif isinstance(task_results, dict):
                url = args.elasticsearch
                if 'id' in task_results.keys():
                    url += '/' + task_results['id']
                requests.post(url, data=json.dumps(task_results))
            else:
                raise NotImplementedError('Task processing should return a list or a dict.')
        pool.close()
        pool.join()
    except KeyboardInterrupt:
        logging.critical('User requested termination.')
        pool.terminate()
        pool.join()


if __name__ == '__main__':
    main()
