from typing import Any, Optional, Union
from pydantic import computed_field, field_validator
import pydantic
import networkx as nx
from matplotlib import pyplot as plt
from uuid import uuid4
import os
import logging

from ..transformers import registered_transformers

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
    min_monitor_interval: float = 0.0
    on_change_only: bool = False
    trace_buffer_size: int = 10000
    trace_port: int = 8100

    @pydantic.field_validator('type')
    def validate_type(cls, v):
        allowed = {'continuous', 'event_driven'}
        if v not in allowed:
            raise ValueError(f'deployment type must be one of {allowed}, got {v!r}')
        return v

    @pydantic.model_validator(mode='after')
    def check_rate(self):
        if self.type == 'continuous' and (self.rate is None or self.rate <= 0):
            raise ValueError(
                f'continuous deployments require a positive rate, got {self.rate!r}'
            )
        return self


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
            if value.pub is not None or str(value.pub).lower() != 'none':
                if isinstance(value.pub, str):
                    value.pub = [value.pub]
                for key2, value2 in self.modules.items():
                    if value2.sub is not None:
                        # normalise them all to lists
                        if isinstance(value2.sub, str):
                            value2.sub = [value2.sub]

                        for pub in value.pub:
                            for sub in value2.sub:
                                # YAML `pub: None` is the string 'None': no topic
                                if (
                                    pub == sub
                                    and str(pub).lower() != 'none'
                                    and value.name != value2.name
                                ):
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

    def isolated_modules(self) -> list[str]:
        """Modules that neither publish to nor subscribe from any other module."""
        return list(nx.isolates(self.graph))

    # field_validator does not run on computed fields, so check after init
    @pydantic.model_validator(mode='after')
    def check_routing(self):
        isolated_nodes = self.isolated_modules()
        if isolated_nodes:
            logging.warning(
                f'Isolated nodes found in routing graph: {isolated_nodes}, these modules '
                'neither publish to nor subscribe from any other module and will '
                'never receive messages'
            )
        return self

    def draw_routing_graph(self):
        G = self.graph
        plt.figure(figsize=(10, 10))
        nx.draw(G, with_labels=True)
        if not os.path.exists('./graphs'):
            os.makedirs('./graphs')
        plt.savefig('./graphs/{}_routing_graph.png'.format(uuid4()))

    def _acyclic_routing(self, G: nx.DiGraph) -> nx.DiGraph:
        """Copy of G with the edges that close cycles removed.

        Pipelines are normally cyclic (an interface publishes the inputs and
        subscribes to the outputs), which topological sorting rejects.  Walk
        from the input modules (subscribed to 'get_all') and drop the edge
        that closes each cycle, so inputs land in the first layer.
        """
        dag = G.copy()
        sources = [
            m.name
            for m in self.modules.values()
            if m.name in dag
            and 'get_all' in ([m.sub] if isinstance(m.sub, str) else (m.sub or []))
        ]
        sources += [n for n in dag if dag.in_degree(n) == 0 and n not in sources]
        while not nx.is_directed_acyclic_graph(dag):
            try:
                cycle = nx.find_cycle(dag, source=sources or None)
            except nx.NetworkXNoCycle:
                # cycle not reachable from the sources
                cycle = nx.find_cycle(dag)
            dag.remove_edge(*cycle[-1][:2])
        return dag

    def save_routing_graph(self, path: str) -> None:
        """Save routing graph to the specified file"""
        plt.figure(figsize=(10, 10))
        G = self.graph
        # Sort based on topology
        for i, l in enumerate(nx.topological_generations(self._acyclic_routing(G))):
            for n in l:
                G.nodes[n]['layer'] = i
        nx.draw(
            G,
            with_labels=True,
            node_size=4096,  # Arbitrary; looks good enough...
            pos=nx.multipartite_layout(
                G, subset_key='layer', align='horizontal', scale=-2
            ),
        )
        plt.savefig(path)
