# vim: tabstop=4 shiftwidth=4 softtabstop=4

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

import logging
import routes

from imagebuilder.api.v1 import builds
from imagebuilder.common import wsgi

logger = logging.getLogger(__name__)

class API(wsgi.Router):

    """WSGI router for Heat v1 API requests."""
    #TODO GetTemplate, ValidateTemplate

    def __init__(self, conf, **local_conf):
        self.conf = conf
        mapper = routes.Mapper()

        builds_resource = builds.create_resource(conf)

        mapper.connect("/build", controller=builds_resource,
                       action="create", conditions=dict(method=["POST"]))
        mapper.connect("/builds", controller=builds_resource,
                       action="list", conditions=dict(method=["GET"]))
        mapper.connect("/build/{build_id}", controller=builds_resource,
                       action="describe", conditions=dict(method=["GET"]))
        mapper.connect("/build", controller=builds_resource,
                       action="update", conditions=dict(method=["PUT"]))

        super(API, self).__init__(mapper)
