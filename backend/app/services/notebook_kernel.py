"""
Persistent Notebook Kernel for data science workflows.
Similar to Jupyter notebook cells - variables persist between executions.
"""

import multiprocessing
import queue
import traceback
import sys
import io
from typing import Dict, Any, Optional
from contextlib import redirect_stdout, redirect_stderr


class NotebookKernel:
    """
    A persistent Python kernel that maintains state between code executions.
    Similar to Jupyter notebook cells.
    """
    
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.globals = {
            '__name__': '__main__',
            '__session_id__': session_id,
        }
        self.locals = {}
        self.execution_count = 0
        self.history = []
        
        # Initialize common data science libraries
        self._init_environment()
    
    def _init_environment(self):
        """Initialize the kernel environment with common libraries."""
        setup_code = """
import os
import sys
import json
import math
import random
import datetime
from datetime import datetime, timedelta
import itertools
import collections
import statistics
import re
import string
import hashlib
import base64
import io
import csv

# Data science libraries
try:
    import numpy as np
except ImportError:
    np = None

try:
    import pandas as pd
except ImportError:
    pd = None

try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from pathlib import Path
    
    # Setup image directory with session ID
    _images_dir = Path("./data/images")
    _session_id = "''' + self.session_id + '''"
    _images_dir.mkdir(parents=True, exist_ok=True)
    
    # Override savefig to add session prefix
    _original_savefig = plt.savefig
    def _session_savefig(fname, *args, **kwargs):
        if fname and not fname.startswith('/'):
            # Extract just the filename (not the path) and add session_id prefix
            import os
            basename = os.path.basename(fname)
            fname = str(_images_dir / (_session_id + "_" + basename))
        result = _original_savefig(fname, *args, **kwargs)
        # Print marker so agent can track the saved image
        print(f"[IMAGE_SAVED] {fname}")
        return result
    plt.savefig = _session_savefig
    
    # Override show to save instead
    def _session_show(*args, **kwargs):
        import uuid
        fig = plt.gcf()
        img_path = str(_images_dir / (_session_id + "_" + uuid.uuid4().hex[:8] + ".png"))
        fig.savefig(img_path, dpi=150, bbox_inches='tight', facecolor='white')
        print(f"[IMAGE_SAVED] {img_path}")
        plt.close(fig)
    plt.show = _session_show
    
except ImportError:
    plt = None

try:
    import seaborn as sns
except ImportError:
    sns = None

# Set default figure size
if plt:
    plt.rcParams['figure.figsize'] = (10, 6)
    plt.rcParams['figure.dpi'] = 100

print(f"Kernel initialized. Available libraries: numpy, pandas, matplotlib, seaborn")
"""
        # Execute setup code silently
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            exec(setup_code, self.globals, self.locals)
            self.globals.update(self.locals)
        except Exception as e:
            pass  # Ignore setup errors
        finally:
            sys.stdout = old_stdout
    
    def get_variables(self) -> Dict[str, Any]:
        """Get current variable names and their types."""
        variables = {}
        for name, value in self.globals.items():
            if not name.startswith('_') and name not in ['__name__', '__session_id__']:
                try:
                    var_type = type(value).__name__
                    variables[name] = {
                        "type": var_type,
                        "repr": repr(value)[:100] + "..." if len(repr(value)) > 100 else repr(value)
                    }
                except:
                    variables[name] = {"type": "unknown", "repr": "..."}
        return variables
    
    def reset(self):
        """Reset the kernel to initial state."""
        self.__init__(self.session_id)
    
    def get_history(self) -> list:
        """Get execution history."""
        return self.history


# Global kernel registry
_kernel_registry: Dict[str, NotebookKernel] = {}


def get_kernel(session_id: str) -> NotebookKernel:
    """Get or create a kernel for a session."""
    if session_id not in _kernel_registry:
        _kernel_registry[session_id] = NotebookKernel(session_id)
    return _kernel_registry[session_id]


def cleanup_kernel(session_id: str):
    """Remove a kernel from registry."""
    if session_id in _kernel_registry:
        del _kernel_registry[session_id]
