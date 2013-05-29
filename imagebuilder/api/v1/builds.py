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

"""
/build endpoint for imagebuilder v1 API
"""
import httplib
import json
import logging
import os
import socket
import sys
import urlparse

import webob
from webob.exc import (HTTPNotFound,
                       HTTPConflict,
                       HTTPBadRequest)

from imagebuilder.common import wsgi
from imagebuilder import MongoPersistentBuildManager
logger = logging.getLogger('imagebuilder.api.v1.builds')


class BuildController(object):

    """
    WSGI controller for builds resource in imagebuilder v1 API

    """

    def __init__(self, options):
        self.options = options
        self.build_manager = MongoPersistentBuildManager.MongoPersistentBuildManager()

    def list(self, req):
        """
        Returns the following information for all builds:
        """
         
        build_list = self.build_manager.builds_from_query({})
        return build_list

    def describe(self, req, build_id):
        """
        Returns the following information for all builds:
        """
        build_list = self.build_manager.build_with_id(build_id)
        return build_list


    def create(self, req):
        """
        Returns the following information for all builds:
        """
        build = {}
        for k, v in req.params.items():
           build[k] = v
        build['state'] = 'BUILDING' 
        return self.build_manager.add_build(build)


    def delete(self, req):
        """
        Returns the following information for all builds:
        """
        logger.info('in api delete ')
        c = engine.get_engine_client(req.context)
        res = c.delete_build(req.params['StackName'])
        if res.status == 200:
            return {'DeleteStackResult': ''}
        else:
            return webob.exc.HTTPNotFound()


def create_resource(options):
    """Builds resource factory method."""
    deserializer = wsgi.JSONRequestDeserializer()
    serializer = wsgi.JSONResponseSerializer()
    return wsgi.Resource(BuildController(options), deserializer, serializer)
