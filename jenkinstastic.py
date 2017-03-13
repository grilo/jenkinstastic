#!/usr/bin/env python

import urlparse
import json
import hashlib
import datetime
import logging
import argparse
import sys

import requests


class Endpoint(object):

    def __init__(self, url):
        if not url.endswith('/'):
            url = url + '/'
        self.url = url + 'api/json'
        for k, v in self.__client(self.url).items():
            self.__dict__[k] = v

    def __client(self, url):
        logging.debug('Requesting: %s', url)
        data = requests.get(url).text
        return json.loads(data)

    def _get_urls(self, name, urls):
        for item in urls:
            obj = Endpoint(item['url'])
            obj.__class__.__name__ = name
            yield obj

    def __getattribute__(self, name):
        attribute = super(Endpoint, self).__getattribute__(name)
        # Make sure we only intercept a very specific set of calls which
        # enable the recursion into the resources which have an 'url' tag
        # tag associated with them.
        if isinstance(attribute, list) and \
                len(attribute) and \
                isinstance(attribute[0], dict) \
                and 'url' in attribute[0].keys():
            return self._get_urls(name, attribute)
        return attribute

    def __repr__(self):
        string = [self.__class__.__name__]
        for k, v in self.__dict__.items():
            string.append('  %s: %s' % (k, v))
        return '\n'.join(string) + '\n'


def generate_build_uid(data):
    h = hashlib.sha1()
    h.update(data['host'] + data['job'] + str(data['buildNumber']) + str(data['buildTimestamp']))
    return h.hexdigest()


def main():

    if sys.version_info < (2,6) or sys.version_info > (2,8):
        raise SystemExit('Sorry, this code needs Python 2.6 or Python 2.7 (current: %s.%s)' % (sys.version_info[0], sys.version_info[1]))

    desc = 'Crawls a Jenkins instance and posts data to elasticsearch.'
    parser = argparse.ArgumentParser(description=desc)

    parser.add_argument('-v', '--verbose', action='store_true', \
        help='Increase output verbosity')
    parser.add_argument('-e', '--elasticsearch', default='http://localhost:9200', \
        help='The Elasticsearch instance where the build info will be POSTed to.')
    parser.add_argument('-j', '--jenkins', default='http://localhost:9090', \
        help='The Jenkins instance to be crawled for build information.')

    args = parser.parse_args()

    logging.basicConfig(format='%(asctime)s::%(levelname)s::%(message)s')
    logging.getLogger().setLevel(getattr(logging, 'INFO'))

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logging.debug('Verbose mode activated.')

    # Sanity check
    if not args.elasticsearch.startswith('http'):
        raise SystemExit('The Elasticsearch instance must start with http')
    if not args.jenkins.startswith('http'):
        raise SystemExit('The Jenkins instance must start with http')

    #args.jenkins = 'https://jenkins.mono-project.com'
    args.jenkins = 'https://hub.spigotmc.org/jenkins'

    j = Endpoint(args.jenkins)
    for job in j.jobs:
        for build in job.builds:

            entry = {}
            entry['host'] = urlparse.urlparse(j.url).netloc.split(':')[0]
            entry['job'] = job.displayName
            entry['buildTimestamp'] = datetime.datetime.utcfromtimestamp(build.timestamp / 1000).isoformat()
            entry['buildDuration'] = build.duration
            entry['buildNumber'] = build.number
            entry['buildResult'] = build.result
            entry['causes'] = []
            entry['testTotalCount'] = 0
            entry['testSkipCount'] = 0
            entry['testFailCount'] = 0

            build_uid = generate_build_uid(entry)

            for action in build.actions:
                if 'causes' in action.keys():
                    logging.debug('Found build triggers, appending to: %s', build_uid)
                    for cause in action['causes']:
                        if 'userName' in cause.keys():
                            entry['causes'].append(cause['userName'])
                        elif '_class' in cause.keys():
                            entry['causes'].append(cause['_class'])

                if 'totalCount' in action.keys():
                    logging.debug('Found test results, appending to: %s', build_uid)
                    entry['testTotalCount'] = action['totalCount']
                    entry['testSkipCount'] = action['skipCount']
                    entry['testFailCount'] = action['failCount']

            if not entry['causes']:
                entry['causes'].append('unknown')
            entry['causes'] = ','.join(entry['causes'])

            logging.debug('POSTing JSON')
            logging.debug(json.dumps(entry, indent=2))
            dump = json.dumps(entry)
            response = requests.post(args.elasticsearch + '/jenkins/builds/' + build_uid, data=dump)
            logging.debug('Elasticsearch code (%i): %s', response.status_code, response.text)
            status = 'created'
            if response.status_code == 200:
                status = 'updated'

            logging.info('Job (%s/%s/%i) in elasticsearch: %s', entry['host'], entry['job'], entry['buildNumber'], status)

if __name__ == '__main__':
    main()
