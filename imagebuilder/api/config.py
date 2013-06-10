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

from oslo.config import cfg
import logging


log = logging.getLogger( __name__)

service_opts = [
    cfg.ListOpt('enabled_apis',
                default=['osib/v1'],
                help='the list of APIs enabled (currently unused)'),
    cfg.ListOpt('enabled_ssl_apis',
                default=[],
                help='the list of APIs enabled via SSL (currently unused)'),
    cfg.StrOpt('osib_listen_host',
               default='0.0.0.0',
               help='host address for imagebuilder REST API'),
    cfg.IntOpt('osib_listen_port',
               default=8080,
               help='port to listen to for imagebuilder REST API'),
    cfg.StrOpt('osib_persistence_backend',
               default='SQLAlchemy',
               help='data manager to use: SQLAlchemy, Mongo')
]
config = cfg.CONF
config.register_opts(service_opts)
#config.import_opt('host', 'imagebuilder.netconf')

# Server Specific Configurations
server = {
    'port': config['osib_listen_port'],
    'host': '0.0.0.0'
}

# Pecan Application Configurations
app = {
    'root': 'imagebuilder.api.controllers.RootController',
    'modules': ['imagebuilder.api'],
    'static_root': '%(confdir)s/public',
    'template_path': '%(confdir)s/api/templates',
    'debug': True,
    'errors': {
        404: '/error/404',
        '__force_dict__': True
    }
}

logging = {
    'loggers': {
        'root': {'level': 'INFO', 'handlers': ['console']},
        'osib': {'level': 'DEBUG', 'handlers': ['console']}
    },
    'handlers': {
        'console': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
            'formatter': 'simple'
        }
    },
    'formatters': {
        'simple': {
            'format': ('%(asctime)s %(levelname)-5.5s [%(name)s]'
                       '[%(threadName)s] %(message)s')
        }
    }
}

# Custom Configurations must be in Python dictionary format::
#
# foo = {'bar':'baz'}
#
# All configurations are accessible at::
# pecan.conf
