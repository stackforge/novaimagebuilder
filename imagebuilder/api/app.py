#
#   Copyright 2013 Red Hat, Inc.
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.


import sys
import os
import logging
import pecan
from imagebuilder import service
from imagebuilder.api import config as pecan_config
from imagebuilder.openstack.common import log
from oslo.config import cfg
from wsgiref import simple_server


def get_pecan_config():
    # Set up the pecan configuration
    filename = pecan_config.__file__.replace('.pyc', '.py')
    return pecan.configuration.conf_from_file(filename)


def setup_app(config):
    if not config:
        config = get_pecan_config()
    pecan.configuration.set_config(dict(config), overwrite=True)
    return pecan.make_app(
        config.app['root'],
        static_root=config.app['static_root'],
        template_path=config.app['template_path'],
        debug=cfg.CONF.debug,
        force_canonical=getattr(config.app, 'force_canonical', True),
    )

def start():
    # Parse OpenStack config file and command line options, then
    # configure logging.
    service.prepare_service(sys.argv)

    # Build the WSGI app
    host, port = cfg.CONF['host'], cfg.CONF['port']
    srvr_config = get_pecan_config()
    srvr_config['server']['host'] = host
    srvr_config['server']['port'] = port
    root = setup_app(srvr_config)
    # Create the WSGI server and start it
    srvr = simple_server.make_server(host, port, root)

    LOG = log.getLogger(__name__)
    LOG.info('Starting server in PID %s' % os.getpid())
    LOG.info("Configuration:")
    cfg.CONF.log_opt_values(LOG, logging.INFO)

    if host == '0.0.0.0':
        LOG.info('serving on 0.0.0.0:%s, view at http://127.0.0.1:%s' %
                 (port, port))
    else:
        LOG.info("serving on http://%s:%s" % (host, port))

    try:
        srvr.serve_forever()
    except KeyboardInterrupt:
        # allow CTRL+C to shutdown without an error
        LOG.info("Shutting down...")