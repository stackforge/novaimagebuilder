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
import pecan
from imagebuilder.api import config as api_config


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

def get_pecan_config():
    # Set up the pecan configuration
    filename = api_config.__file__.replace('.pyc', '.py')
    return pecan.configuration.conf_from_file(filename)


def setup_app(config):
    get_pecan_config()
    return pecan.make_app(
        config.app['root'],
        static_root=config.app['static_root'],
        template_path=config.app['template_path'],
        logging=getattr(config, 'logging', {}),
        debug=getattr(config.app, 'debug', False),
        force_canonical=getattr(config.app, 'force_canonical', True),
        guess_content_type_from_ext=getattr(
            config.app,
            'guess_content_type_from_ext',
            True),
    )
