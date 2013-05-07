#!/usr/bin/env python
import gflags
import os
import sys
import time

from ct.dashboard import grapher
from ct.client import log_client
from ct.client import sqlite_db
from ct.proto import client_pb2
from wsgiref import simple_server

FLAGS = gflags.FLAGS

gflags.DEFINE_string('dashboard_host', "127.0.0.1", "Dashboard server host")
gflags.DEFINE_integer('dashboard_port', 8000, "Dashboard server port")
gflags.DEFINE_spaceseplist('ct_server_list', "ct.googleapis.com/pilot",
                           "List of CT servers to monitor")
gflags.DEFINE_string('ct_sqlite_db', "/tmp/ct", "Location of the CT database")

class DashboardServer(object):
    template_pages = {"default", "sth"}

    """A simple web application for serving status pages."""
    def __init__(self, host, port, db):
        self.host = host
        self.port = port
        self.db = db
        self.grapher = grapher.GvizGrapher()
        self.templates = {}
        self._read_templates()
        self.favicon = ""
        self._read_favicon()

    def _read_templates(self):
        """Read the HTML templates from the templates/ directory."""
        for page in DashboardServer.template_pages:
            template_file = os.path.join(os.path.dirname(__file__),
                                         "templates/%s.html" % page)
            self.templates[page] = open(template_file, 'r').read()

    def _read_favicon(self):
        """Read favicon.ico."""
        favicon_file = os.path.join(os.path.dirname(__file__), "favicon.ico")
        self.favicon = open(favicon_file, 'rb').read()

    def __repr__(self):
        return "%r(%r:%r)" % (self.__class__.__name__,
                              self.host, self.port)

    def __str__(self):
        return "%s(%s:%d)" % (self.__class__.__name__,
                              self.host, self.port)

    def __call__(self, environ, start_response):
        page = environ.get('PATH_INFO', '').strip('/')
        # Serve the default page when there is no match
        status = '200 OK'
        if page == "favicon.ico":
                headers = [('Content-type', 'image/png')]
                start_response(status, headers)
                return self.favicon

        status = '200 OK'
        headers = [('Content-type', 'text/html')]
        start_response(status, headers)
        varz = {}
        varz["current_time"] = "\nCurrent time: %s\n" % time.strftime("%c")
        if page == "sth":
            self._fill_sth_template(varz)
            return self.templates["sth"] % varz
        else:
            self._fill_default_template(varz)
            return self.templates["default"] % varz

    def _fill_default_template(self, varz):
        """Update the varz with variables required by the default template."""
        varz["pages"] = """<a href=http://%s:%d/sth>
                        The Signed Tree Head Dashboard</a>\n""" % (
            self.host, self.port)

    def _fill_sth_template(self, varz):
        # TODO(ekasper): graph all logs
        server_id = FLAGS.ct_server_list[0]
        varz["log"] = server_id
        one_week_ago = (time.time() - 7*24*60*60)*1000
        columns = [("timestamp", "timestamp_ms", "Timestamp"),
                   ("tree_size", "number", "Tree size")]
        sth_to_show = self.db.scan_latest_sth_range(server_id,
                                                    start=one_week_ago,
                                                    limit=1000)
        varz["json"] = self.grapher.make_table(sth_to_show, columns,
                                               order_by="timestamp")

    def run(self):
        """Set up the HTTP server and loop forever."""
        httpd = simple_server.make_server(self.host, self.port, self)
        print "Serving on http://%s:%d" % (self.host, self.port)
        httpd.serve_forever()

if __name__ == "__main__":
    sys.argv = FLAGS(sys.argv)
    sqlitedb = sqlite_db.SQLiteDB(FLAGS.ct_sqlite_db)
    for server in FLAGS.ct_server_list:
      log = client_pb2.CtLogMetadata()
      log.log_server = server
      sqlitedb.add_log(log)
    prober = log_client.LogProber(FLAGS.ct_server_list, sqlitedb)
    prober.setDaemon(True)
    prober.start()
    server = DashboardServer(FLAGS.dashboard_host, FLAGS.dashboard_port,
                             sqlitedb)
    server.run()
