#!/usr/bin/env python
# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
# Copyright 2011 OpenStack LLC.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.
"""Starter script for Nova API.

Starts both the EC2 and OpenStack APIs in separate greenthreads.

"""

import sys

from oslo.config import cfg

from imagebuilder import config
from imagebuilder.openstack.common import log as logging
from imagebuilder import service
from imagebuilder import utils

CONF = cfg.CONF
CONF.import_opt('enabled_apis', 'imagebuilder.service')
CONF.import_opt('enabled_ssl_apis', 'imagebuilder.service')


def main():
    config.parse_args(sys.argv)
    logging.setup("imagebuilder")
    utils.monkey_patch()

    launcher = service.ProcessLauncher()
    for api in CONF.enabled_apis:
        import pdb;pdb.set_trace()
        should_use_ssl = api in CONF.enabled_ssl_apis
        server = service.WSGIService(api, use_ssl=should_use_ssl)
        launcher.launch_server(server, workers=server.workers or 1)
    launcher.wait()
