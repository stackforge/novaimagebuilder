import os
import socket

from oslo.config import cfg

from imagebuilder.openstack.common import log



CLI_OPTIONS = [
    cfg.StrOpt('host',
               default='0.0.0.0',
               help='IP or hostname to run the REST api on.'),
    cfg.IntOpt('port',
               default=8080,
               help='Port number to run the REST server on.'),

]
cfg.CONF.register_cli_opts(CLI_OPTIONS)


def prepare_service(argv=[]):
    cfg.set_defaults(log.log_opts,
                     default_log_levels=['sqlalchemy=WARN',
                                         'eventlet.wsgi.server=WARN'
                                         ])
    cfg.CONF(argv[1:], project='imagebuilder')
    log.setup('imagebuilder')

