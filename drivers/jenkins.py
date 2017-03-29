#!/usr/bin/env python

import json
import datetime
import logging
import urlparse
import hashlib

import requests


def get_type():
    return 'builds'

def get_tasks_fast(url, username=None, password=None, resume_id=None):
    logging.warning('Jenkins driver ignores the resume_id parameter.')
    # Much faster but loads huge amounts of data into memory if the jenkins
    # instance is very large
    if not url.endswith('/'):
        url += '/'
    url += 'api/json?depth=2'
    logging.debug('Requesting: %s', url)
    data = json.loads(requests.get(url, verify=False, auth=(username, password)).text)
    for job in data['jobs']
        yield job

def get_tasks(url, username=None, password=None, resume_id=None):
    logging.warning('Jenkins driver ignores the resume_id parameter.')
    if not url.endswith('/'):
        url += '/'
    url += 'api/json'
    logging.debug('Requesting: %s', url)
    data = json.loads(requests.get(url, verify=False, auth=(username, password)).text)
    for job in data['jobs']:
        job_url = job['url'] + 'api/json?depth=2'
        yield json.loads(requests.get(job_url).text)

def process_task(jenkins_jobs):
    builds =  []
    logging.debug('Processing build batch...')
    for build in jenkins_jobs['builds']:
        host = urlparse.urlparse(build['url'])
        name = build['fullDisplayName'].rstrip(build['displayName'])
        builds.append(get_build(host, name, build))
    logging.info('Found (%i) builds.', len(builds))
    return builds

def get_build(host, job_name, build):

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
        'id': None
    }

    h = hashlib.sha1()
    h.update(str(host) + str(job_name) + str(props['number']) + props['timestamp'])
    props['id'] = h.hexdigest()

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

    return props
