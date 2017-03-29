# jenkinstastic
Collects data from a service instance and feeds the data to an elasticsearch cluster.

## Usage
```bash
python main.py -d <driver> -l <service url>

python main.py -d jenkins -l https://your.jenkins.instance

python main.py -d git -l https://your.git.instance
```

## Why
There is a [jenkins-logstash](https://github.com/jenkinsci/logstash-plugin) plugin, but this will work
for new builds. While the plugin is, in fact, able to interact directly with your elasticsearch instance
(instead of actually requiring logstash), it has a limitation. If you have an existing Jenkins instance,
the historic stuff will never find its way into your elasticsearch.

jenkinstatic (a play on jenkins and mr. fantastic, because he's elastic, sounded better at the time)
allows you to setup a simple cron (perhaps a Jenkins job even) which will occasionally crawl your
jenkins instance and submit the already existing build data.

Which means it doesn't work in real-time, which also means the delay is entirely up to you. Perhaps
you want to crawl your jenkins instance at times of lower load.

The utility has an UID generator to minimize the amount of duplicate data being submitted. With the
UID being provided, elasticsearch itself will ensure that existing entries are updated instead of
created/duplicated.

## How

The crawling is done recursively by inspecting "url" entries within the response structure.
The request to Jenkins is a simple GET request, requesting the api/json as response.

The found data will then be POSTed to elasticsearch. An example:

```json
{
  "testFailCount": 1, 
  "buildResult": "SUCCESS", 
  "job": "CraftBukkit-RSS", 
  "buildDuration": 593, 
  "buildNumber": 695, 
  "host": "jenkins.host.com", 
  "testSkipCount": 3, 
  "causes": "hudson.triggers.SCMTrigger$SCMTriggerCause,SomeUser", 
  "testTotalCount": 15, 
  "buildTimestamp": "2017-01-19T23:16:08"
}
```

Each build entry found will have an unique ID depending on the following parameters:
 - Jenkins Host
 - Jenkins Job Name
 - Build Number
 - Build Timestamp

All of the above data will be concatenated and digested with a SHA1 sum to minimize the
potential amount of duplicate entries (which would otherwise contaminate your elasticsearch
instance).

There is no strong coupling with elasticsearch, meaning that it's possible to point the
utility to any HTTP API which fulfills the same contract.
