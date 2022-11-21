from typing import Deque, Dict, List, Type, Union

import numpy as np
import pandas as pd
import torch
from ordered_set import OrderedSet
from river import base
from river.base.typing import RegTarget


def dict2tensor(
        x: dict,
        device: str = "cpu",
        dtype: torch.dtype = torch.float32
) -> torch.Tensor:
    """
    Convert a dictionary to a tensor.

    Parameters
    ----------
    x
        Dictionary.
    device
        Device.
    dtype
        Dtype.

    Returns
    -------
        torch.Tensor
    """
    return torch.tensor([list(x.values())], device=device, dtype=dtype)


def float2tensor(
        y: Union[float, int, RegTarget],
        device="cpu",
        dtype=torch.float32
) -> torch.Tensor:
    """
    Convert a float to a tensor.

    Parameters
    ----------
    y
        Float.
    device
        Device.
    dtype
        Dtype.

    Returns
    -------
        torch.Tensor
    """
    return torch.tensor([[y]], device=device, dtype=dtype)


def deque2rolling_tensor(
    window: Deque,
    device="cpu",
    dtype=torch.float32,
) -> torch.Tensor:
    """
    Convert a dictionary to a rolling tensor.

    Parameters
    ----------
    x
        Dictionary.
    window
        Rolling window.
    device
        Device.
    dtype
        Dtype.

    Returns
    -------
        torch.Tensor
    """
    output = torch.tensor(window, device=device, dtype=dtype)
    return torch.unsqueeze(output, 1)


def df2tensor(
        X: pd.DataFrame,
        device="cpu",
        dtype=torch.float32
) -> torch.Tensor:
    """
    Convert a dataframe to a tensor.
    Parameters
    ----------
    X
        Dataframe.
    device
        Device.
    dtype
        Dtype.

    Returns
    -------
        torch.Tensor
    """
    return torch.tensor(X.values, device=device, dtype=dtype)


def labels2onehot(
    y: Union[base.typing.ClfTarget, List],
    classes: OrderedSet,
    n_classes: int = None,
    device="cpu",
    dtype=torch.float32,
) -> torch.Tensor:
    """
    Convert a label or a list of labels to a one-hot encoded tensor.

    Parameters
    ----------
    y
        Label or list of labels.
    classes
        Classes.
    n_classes
        Number of classes.
    device
        Device.
    dtype
        Dtype.

    Returns
    -------
        torch.Tensor
    """
    if n_classes is None:
        n_classes = len(classes)
    if isinstance(y, list):
        onehot = torch.zeros(len(y), n_classes, device=device, dtype=dtype)
        pos_idcs = [classes.index(y_i) for y_i in y]
        for i, pos_idx in enumerate(pos_idcs):
            if pos_idx < n_classes:
                onehot[i, pos_idx] = 1
    else:
        onehot = torch.zeros(1, n_classes, device=device, dtype=dtype)
        pos_idx = classes.index(y)
        if pos_idx < n_classes:
            onehot[0, pos_idx] = 1

    return onehot


def output2proba(
    preds: torch.Tensor, classes: OrderedSet, with_logits=False
) -> List:
    if with_logits:
        if preds.shape[-1] >= 1:
            preds = torch.softmax(preds, dim=-1)
        else:
            preds = torch.sigmoid(preds)

    preds = preds.detach().numpy()
    if preds.shape[1] == 1:
        preds = np.hstack((preds, 1 - preds))
    n_unobserved_classes = preds.shape[1] - len(classes)
    if n_unobserved_classes > 0:
        classes = list(classes)
        classes.extend(
            [f"unobserved {i}" for i in range(n_unobserved_classes)]
        )
    probas = (
        dict(zip(classes, preds[0]))
        if preds.shape[0] == 1
        else [dict(zip(classes, pred)) for pred in preds]
    )
    return probas
