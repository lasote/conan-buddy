# coding=utf-8

from flask import Flask, render_template, redirect, abort
from flask_bootstrap import Bootstrap

from util import generate_data, group_queue_issues, get_data, get_triaging_without_user, \
    get_queue_with_user

app = Flask(__name__)
Bootstrap(app)


@app.context_processor
def utility_processor():
    def decorate_label(label):
        if label is None:
            return ""
        elif label == "high":
            return '<span class="label label-danger">high</span>'
        elif label == "medium":
            return '<span class="label label-warning">medium</span>'
        elif label == "low":
            return '<span class="label label-info">low</span>'
        elif label == "huge":
            return '<span class="label label-dark">huge</span>'
        return '<span class="label label-primary">%s</span>' % label

    def to_id(text):
        return text.strip().replace(" ", "_")

    def print_list(the_list):
        return ",".join(decorate_label(i) for i in the_list)
    return dict(decorate_label=decorate_label, to_id=to_id, print_list=print_list)


@app.route('/refresh')
def refresh_data():
    generate_data()
    return redirect("/")


@app.route('/')
def index():
    try:
        issues = get_data()
        g = group_queue_issues(issues)
    except Exception as e:
        abort(500, str(e))
    else:
        return render_template('issues.html', groups=g)


@app.route('/sanity')
def sanity():
    t = get_triaging_without_user()
    t2 = get_queue_with_user()
    return render_template('sanity.html', triaging_without_user=t, queue_with_user=t2)
