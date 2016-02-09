# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.
from collections import namedtuple

from oslo_log import log as logging

from smaug.i18n import _

_GraphBuilderContext = namedtuple("_GraphBuilderContext", (
    "source_set",
    "encounterd_set",
    "finished_nodes",
    "get_child_nodes",
))

GraphNode = namedtuple("GraphNode", (
    "value",
    "child_nodes",
))

LOG = logging.getLogger(__name__)


class FoundLoopError(RuntimeError):
    def __init__(self):
        super(FoundLoopError, self).__init__(
            _("A loop was found in the graph"))


def _build_graph_rec(context, node):
    LOG.trace("Entered node: %s", node)
    source_set = context.source_set
    encounterd_set = context.encounterd_set
    finished_nodes = context.finished_nodes
    LOG.trace("Gray set is %s", encounterd_set)
    if node in encounterd_set:
        raise FoundLoopError()

    LOG.trace("Black set is %s", finished_nodes.keys())
    if node in finished_nodes:
        return finished_nodes[node]

    LOG.trace("Change to gray: %s", node)
    encounterd_set.add(node)
    child_nodes = context.get_child_nodes(node)
    LOG.trace("child nodes are ", child_nodes)
    # If we found a parent than this is not a source
    source_set.difference_update(child_nodes)
    child_list = []
    for child_node in child_nodes:
        child_list.append(_build_graph_rec(context, child_node))

    LOG.trace("Change to black: ", node)
    encounterd_set.discard(node)
    graph_node = GraphNode(value=node, child_nodes=tuple(child_list))
    finished_nodes[node] = graph_node

    return graph_node


def build_graph(start_nodes, get_child_nodes_func):
    context = _GraphBuilderContext(
        source_set=set(start_nodes),
        encounterd_set=set(),
        finished_nodes={},
        get_child_nodes=get_child_nodes_func,
    )

    result = []
    for node in start_nodes:
        result.append(_build_graph_rec(context, node))

    assert(len(context.encounterd_set) == 0)

    return [item for item in result if item.value in context.source_set]
