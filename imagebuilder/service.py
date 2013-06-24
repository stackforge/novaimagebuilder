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
from oslo.config import cfg
from imagebuilder.openstack.common import log
from imagebuilder.openstack.common import gettextutils


cfg.CONF.register_opts([
    cfg.StrOpt('host',
               default='0.0.0.0',
               help='host address for imagebuilder REST API'),
    cfg.IntOpt('port',
               default=8080,
               help='port to listen to for imagebuilder REST API'),
    cfg.StrOpt('persistence_backend',
               default='SQLAlchemy',
               help='data manager to use: SQLAlchemy, Mongo')
])

def prepare_service(argv=None):
    gettextutils.install('imagebuilder')
    cfg.set_defaults(log.log_opts,
                     default_log_levels=['sqlalchemy=WARN',
                                         'eventlet.wsgi.server=WARN'
                                         ])
    if argv is None:
        argv = sys.argv
    cfg.CONF(argv[1:], project='imagebuilder')
    log.setup('imagebuilder')
