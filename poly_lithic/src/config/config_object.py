from typing import Any, Optional, Union
from pydantic import computed_field
import pydantic
import networkx as nx
from ..transformers import registered_transformers
from matplotlib import pyplot as plt
from uuid import uuid4
import os
import logging

allowed_transformers = list(registered_transformers.keys())


class ModuleConfig(pydantic.BaseModel):
    type: str
    name: str
    pub: Optional[Union[str, list]] = None
    sub: Optional[Union[str, list]] = None
    module_args: Optional[Union[dict[str, Union[str, dict, bool]], str]] = None
    config: Any = None  # kind of a free for all for now but we can narrow down the specifics later

    @pydantic.field_validator('module_args', mode='before')
    def validate_module_args(cls, v):
        if isinstance(v, str):
            return {}
        return v


class DeploymentConfig(pydantic.BaseModel):
    type: str
    rate: Optional[Union[float, int]] = None


class ConfigObject(pydantic.BaseModel):
    deployment: DeploymentConfig
    modules: dict[str, ModuleConfig]

    class Config:
        arbitrary_types_allowed = True  # to allow nx.DiGraph

    @computed_field(return_type=nx.DiGraph)
    @property
    def graph(self):
        G = nx.DiGraph()
        nodes = []
        edges = []
        # to collect edges we need to go through each item , look at what its publishing and find matching subsribers, this will form an edge
        for key, value in self.modules.items():
            if value.pub is not None or value.pub.lower() != 'none':
                if isinstance(value.pub, str):
                    value.pub = [value.pub]
                for key2, value2 in self.modules.items():
                    if value2.sub is not None:
                        # normalise them all to lists
                        if isinstance(value2.sub, str):
                            value2.sub = [value2.sub]

                        for pub in value.pub:
                            for sub in value2.sub:
                                if pub == sub and value.name != value2.name:
                                    edges.append((value.name, value2.name))

            nodes.append(value.name)

        logging.debug(f'Nodes: {nodes}')
        logging.debug(f'Edges: {edges}')
        nodes = list(set(nodes))
        nodes = [x for x in nodes if x is not None]
        edges = [tuple(x) for x in edges]

        G.add_nodes_from(nodes)
        G.add_edges_from(edges)
        return G

    @pydantic.field_validator('graph')
    def check_routing(cls, v):
        isolated_nodes = list(nx.isolates(v))
        if isolated_nodes:
            raise ValueError(
                f'Isolated nodes found in routing graph: {isolated_nodes}, this means that a modules is niether a publisher or subscriber to any other module'
            )
        return v

    def draw_routing_graph(self):
        G = self.graph
        plt.figure(figsize=(10, 10))
        nx.draw(G, with_labels=True)
        if not os.path.exists('./graphs'):
            os.makedirs('./graphs')
        plt.savefig('./graphs/{}_routing_graph.png'.format(uuid4()))
