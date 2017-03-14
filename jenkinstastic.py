#!/usr/bin/env python

import json
import hashlib
import datetime
import logging
import argparse
import sys
import signal
import multiprocessing

import requests

def get_builds(url):
    if not url.endswith('/'):
        url += '/'
    url += 'api/json?depth=2'
    logging.debug('Requesting: %s', url)
    data = requests.get(url).text
    return json.loads(data)

class JenkinsClient(object):

    def __init__(self, url):
        if not url.endswith('/'):
            url += '/'
        self.url = url

    def get_jobs(self):
        url = self.url + 'api/json'
        data = requests.get(url).text
        jobs = [job['url'] for job in json.loads(data)['jobs']]
        logging.info('Found (%i) jobs from: %s', len(jobs), url)
        return jobs


class JenkinsBuild(object):

    def __init__(self, host, job_name, build):

        props = {
            'host': host,
            'name': job_name,
            'timestamp': datetime.datetime.utcfromtimestamp(build['timestamp'] / 1000).isoformat(),
            'duration': build['duration'],
            'number': build['number'],
            'result': build['result'],
            'causes': [],
            'testTotalCount': 0,
            'testSkipCount': 0,
            'testFailCount': 0,
        }

        for action in build['actions']:
            if 'causes' in action.keys():
                for cause in action['causes']:
                    true_cause = 'unknown'
                    if 'userName' in cause.keys():
                        true_cause = cause['userName']
                    elif '_class' in cause.keys():
                        true_cause = cause['_class']
                    if not true_cause in props['causes']:
                        props['causes'].append(true_cause)

            if 'totalCount' in action.keys():
                props['testTotalCount'] = action['totalCount']
                props['testSkipCount'] = action['skipCount']
                props['testFailCount'] = action['failCount']

        if not props['causes']:
            props['causes'].append('unknown')
        props['causes'] = ','.join(props['causes'])

        self.props = props

    def __getattr__(self, name):
        if name in self.props.keys():
            return self.props[name]

    def serialize(self):
        return json.dumps(self.props, indent=2)


class ElasticsearchClient(object):

    def __init__(self, url):
        if not url.endswith('/'):
            url += '/'
        self.url = url

    def _uid(self, build):
        h = hashlib.sha1()
        h.update(build.host + build.name + str(build.number) + build.timestamp)
        return h.hexdigest()

    def post(self, build):
        serialized = build.serialize()
        logging.debug('POSTing: \n %s', serialized)
        return requests.post(self.url + 'jenkins/builds/' + self._uid(build), data=serialized)



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

    elastic_client = ElasticsearchClient(args.elasticsearch)
    jenkins_client = JenkinsClient(args.jenkins)

    def init_worker():
        signal.signal(signal.SIGINT, signal.SIG_IGN)
    pool = multiprocessing.Pool(initializer=init_worker)

    try:
        count = 0
        for result in pool.imap_unordered(get_builds, jenkins_client.get_jobs()):
            job_name = result['displayName']
            logging.info('[%i] Builds found for (%s): %i', count, job_name, len(result['builds']))
            for build in result['builds']:
                jenkins_build = JenkinsBuild(args.jenkins, job_name, build)
                response = elastic_client.post(jenkins_build)
                status = 'created'
                if response.status_code == 200:
                    status = 'updated'
                logging.debug('Job (%s/%s/%i) in elasticsearch: %s', \
                    jenkins_build.host, \
                    jenkins_build.name, \
                    jenkins_build.number, status)
            count += 1
        pool.close()
        pool.join()
    except KeyboardInterrupt:
        logging.critical('User requested termination.')
        pool.terminate()
        pool.join()


if __name__ == '__main__':
    main()
