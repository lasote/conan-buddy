import json
import os
from collections import defaultdict
from collections import namedtuple

import redis
from github import Github

REDIS_URL = os.environ.get("REDIS_URL")
REDIS_CLIENT = redis.from_url(REDIS_URL) if REDIS_URL else None
GH_TOKEN = os.getenv("GH_TOKEN")
REPO = os.getenv("REPO", "conan-io/conan")

group_prefix = "type:"
queue_label = "stage: queue"
triaging_label = "stage: triaging"
stage_labels = (queue_label, )

data_file = "data.json"

Label = namedtuple("Label", "title color")


class ConanIssue(object):

    def __init__(self, gh_issue=None, with_assignees=False):
        self.url = gh_issue.html_url if gh_issue else None
        self.labels = [Label(l.name, l.color) for l in gh_issue.get_labels()] if gh_issue else None
        self.title = gh_issue.title if gh_issue else None
        self.milestone = gh_issue.milestone.title if gh_issue and gh_issue.milestone else None
        self.tag_values = {"priority":  {"low": 1, "medium": 2, "high": 3, "critical": 10},
                           "complex": {"low": 1, "medium": 2, "high": 3, "huge": 10, None: 3}}
        self._priority_value = self._complexity_value = None
        if with_assignees:
            self.assignees = [a.login for a in gh_issue.assignees] if gh_issue else None
        else:
            self.assignees = []
        self.number = gh_issue.number if gh_issue else None
        self.component = ""

    @staticmethod
    def loads(data):
        ret = ConanIssue()
        ret.url = data["url"]
        ret.labels = [Label(*d) for d in data["labels"]]
        ret.title = data["title"]
        ret.milestone = data["milestone"]
        ret.assignees = data["assignees"]
        ret.number = data["number"]
        ret.component = ""
        if ret.labels:
            components = [label.title for label in ret.labels if label.title.startswith("component:")]
            ret.component = components[0] if components else ""
        return ret

    def serialize(self):
        return {"url": self.url, "labels": self.labels, "title": self.title,
                "milestone": self.milestone, "assignees": self.assignees, "number": self.number}

    def _get_tag_value(self, prefix):
        label = next((t for t in self.labels if t.title.startswith(prefix)), None)
        if label is None:
            print("Issue not labeled correctly: %s" % self.url)
            return None
        tmp = label.title.split(prefix)[1].strip()
        return tmp

    @property
    def priority_value(self):
        try:
            if not self._priority_value:
                tmp = self._get_tag_value("priority:")
                self._priority_value = float(self.tag_values.get("priority", 1)[tmp])
        except Exception as e:
            msg = "Error processing priority for: %s" % self.url
            print(msg)
            print(e)
            raise Exception(msg)
        return self._priority_value

    @property
    def complexity_value(self):
        if not self._complexity_value:
            tmp = self._get_tag_value("complex:")
            self._complexity_value = float(self.tag_values["complex"][tmp])
        return self._complexity_value

    @property
    def priority_tag(self):
        return self._get_tag_value("priority:")

    @property
    def complexity_tag(self):
        return self._get_tag_value("complex:")


def generate_data():
    tmp = Github(GH_TOKEN)
    repo = tmp.get_repo(REPO)
    issues = []
    for l in stage_labels:
        label = repo.get_label(l)
        issues.extend(repo.get_issues(labels=[label], state="open"))
    data = []
    ret = []
    for issue in issues:
        e = ConanIssue(issue)
        ret.append(e)
        data.append(e.serialize())
    if REDIS_CLIENT:
        REDIS_CLIENT.set(data_file, json.dumps(data))
    else:
        with open(data_file, "w") as f:
            f.write(json.dumps(data))
    return ret


def get_data():
    tmp = None
    if REDIS_CLIENT:
        tmp = REDIS_CLIENT.get(data_file)
    else:
        if os.path.exists(data_file):
            with open(data_file, "r") as f:
                tmp = f.read()
    if not tmp:
        return generate_data()
    else:
        return [ConanIssue.loads(e) for e in json.loads(tmp)]


def rate_issue(conan_issue):
    return conan_issue.priority_value / conan_issue.complexity_value


def group_queue_issues(issues):

    groups = defaultdict(list)
    for issue in issues:
        if queue_label in [l.title for l in issue.labels]:
            for label in issue.labels:
                label_name = label.title
                if label_name.startswith(group_prefix):
                    groups[label_name.split(group_prefix)[1]].append(issue)

    ret = {}
    for key, issues in groups.items():
        ret[key] = [[issue, rate_issue(issue)]
                    for issue in sorted(issues, key=lambda x: rate_issue(x), reverse=True)]
    return ret


def get_triaging_without_user():
    tmp = Github(GH_TOKEN)
    repo = tmp.get_repo(REPO)

    label = repo.get_label(triaging_label)
    issues = repo.get_issues(labels=[label], assignee="none")
    return [ConanIssue(i) for i in issues]


def get_triaging_by_user():
    users_triaging = defaultdict(lambda: 0)
    tmp = Github(GH_TOKEN)
    repo = tmp.get_repo(REPO)

    label = repo.get_label(triaging_label)
    issues = repo.get_issues(labels=[label])
    for i in issues:
        users_triaging[i.assignees[0]] += 1
    return users_triaging


def get_queue_with_user():
    tmp = Github(GH_TOKEN)
    repo = tmp.get_repo(REPO)

    label = repo.get_label(queue_label)
    issues = repo.get_issues(labels=[label], assignee="*", milestone="none")

    return [i for i in [ConanIssue(_i, with_assignees=True)
                        for _i in issues] if i.assignees[0] != "markgalpin"]
