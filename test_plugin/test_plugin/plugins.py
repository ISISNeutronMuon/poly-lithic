"""
Plugin implementations for test_plugin.

This module contains examples of all three plugin types.
Comment out or delete the ones you don't need.
"""

import time
from typing import Dict, Any, Tuple

# Check if these imports are working - this is likely where the issue is
try:
    from poly_lithic.src.interfaces.BaseInterface import BaseInterface
    from poly_lithic.src.transformers.BaseTransformers import BaseTransformer
    from poly_lithic.src.model_utils.ModelGetterBase import ModelGetterBase
except ImportError as e:
    print(f"Import error in test_plugin.plugins: {e}")
    raise


# ============================================================================
# Interface Plugin Example
# ============================================================================

class CustomInterface(BaseInterface):
    """
    Example interface plugin for test_plugin.
    
    Interfaces connect to external systems for reading/writing data.
    Comment out this class if you don't need an interface plugin.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the interface.
        
        Args:
            config: Configuration dictionary containing:
                - variables: Dict of variable configurations
                - host: Optional host/connection info
                - port: Optional port number
                - timeout: Optional timeout in seconds
        """
        super().__init__(config)
        self.config = config
        self.variables = config.get('variables', {})
        
        # For demonstration, we'll use a simple in-memory store
        self._data_store = {}
    
    def get(self, variable: str) -> Tuple[str, Dict[str, Any]]:
        """Get a variable value from the external system."""
        value = self._data_store.get(variable, 0.0)
        return variable, {
            "value": value,
            "timestamp": time.time(),
            "status": "OK"
        }
    
    def put(self, variable: str, value: Any) -> Dict[str, Any]:
        """Set a variable value in the external system."""
        self._data_store[variable] = value
        return {variable: value}
    
    def connect(self) -> None:
        """Establish connection to the external system."""
        pass
    
    def disconnect(self) -> None:
        """Close connection to the external system."""
        pass


# ============================================================================
# Transformer Plugin Example
# ============================================================================

class CustomTransformer(BaseTransformer):
    """
    Example transformer plugin for test_plugin.
    
    Transformers modify data between reading and model input.
    Comment out this class if you don't need a transformer plugin.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize the transformer."""
        super().__init__(config)
        self.config = config
        self.scale = config.get('scale', 1.0)
        self.offset = config.get('offset', 0.0)
    
    def transform(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Transform input data."""
        transformed = {}
        for key, value in input_data.items():
            if isinstance(value, (int, float)):
                transformed[key] = value * self.scale + self.offset
            else:
                transformed[key] = value
        return transformed
    
    def inverse_transform(self, output_data: Dict[str, Any]) -> Dict[str, Any]:
        """Apply inverse transformation to output data."""
        inverse_transformed = {}
        for key, value in output_data.items():
            if isinstance(value, (int, float)) and self.scale != 0:
                inverse_transformed[key] = (value - self.offset) / self.scale
            else:
                inverse_transformed[key] = value
        return inverse_transformed


# ============================================================================
# Model Getter Plugin Example
# ============================================================================

class CustomModelGetter(ModelGetterBase):
    """
    Example model getter plugin for test_plugin.
    
    Model getters load ML models from various sources.
    Comment out this class if you don't need a model getter plugin.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize the model getter."""
        super().__init__(config)
        self.config = config
        self.model_path = config.get('model_path')
        self.model_type = config.get('model_type', 'pickle')
        self.device = config.get('device', 'cpu')
    
    def load_model(self) -> Any:
        """Load and return the model."""
        import pickle
        if self.model_path is None:
            raise ValueError("model_path must be specified in config")
        
        with open(self.model_path, 'rb') as f:
            model = pickle.load(f)
        
        return model
    
    def get_model_info(self) -> Dict[str, Any]:
        """Get information about the model."""
        return {
            'model_path': self.model_path,
            'model_type': self.model_type,
            'device': self.device,
            'version': self.config.get('version', 'unknown'),
        }
    
    def validate_model(self, model: Any) -> bool:
        """Validate that the loaded model is correct."""
        return model is not None