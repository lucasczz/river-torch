from typing import Callable, Dict, List, Type, Union

import pandas as pd
import torch
from river import base
from river.base.typing import ClfTarget
from torch import nn

from river_torch.base import DeepEstimator
from river_torch.utils.tensor_conversion import (df2tensor, dict2tensor,
                                                 labels2onehot, output2proba)


class Classifier(DeepEstimator, base.Classifier):
    """
        Wrapper for PyTorch classification models that automatically handles increases in the number of classes by adding output neurons in case the number of observed classes exceeds the current number of output neurons.

        Parameters
        ----------
        module
            Torch Module that builds the autoencoder to be wrapped. The Module should accept parameter `n_features` so that the returned model's input shape can be determined based on the number of features in the initial training example.
        loss_fn
            Loss function to be used for training the wrapped model. Can be a loss function provided by `torch.nn.functional` or one of the following: 'mse', 'l1', 'cross_entropy', 'binary_crossentropy', 'smooth_l1', 'kl_div'.
        optimizer_fn
            Optimizer to be used for training the wrapped model. Can be an optimizer class provided by `torch.optim` or one of the following: "adam", "adam_w", "sgd", "rmsprop", "lbfgs".
        lr
            Learning rate of the optimizer.
        device
            Device to run the wrapped model on. Can be "cpu" or "cuda".
        seed
            Random seed to be used for training the wrapped model.
        **net_params
            Parameters to be passed to the `build_fn` function aside from `n_features`.

        Examples
        --------
    >>> from river import metrics, preprocessing, compose, datasets
    >>> from river_torch import classification
    >>> from torch import nn
    >>> from torch import manual_seed

    >>> _ = manual_seed(42)

    >>> class MyModule(nn.Module):
    ...     def __init__(self, n_features):
    ...         super(MyModule, self).__init__()
    ...         self.dense0 = nn.Linear(n_features,5)
    ...         self.nonlin = nn.ReLU()
    ...         self.dense1 = nn.Linear(5, 2)
    ...         self.softmax = nn.Softmax(dim=-1)
    ...
    ...     def forward(self, X, **kwargs):
    ...         X = self.nonlin(self.dense0(X))
    ...         X = self.nonlin(self.dense1(X))
    ...         X = self.softmax(X)
    ...         return X

    >>> model_pipeline = compose.Pipeline(
    ...     preprocessing.StandardScaler,
    ...     Classifier(module=MyModule,loss_fn="binary_cross_entropy",optimizer_fn='adam')
    ... )


    >>> dataset = datasets.Phishing()
    >>> metric = metrics.Accuracy()

    >>> for x, y in dataset:
    ...     y_pred = model_pipeline.predict_one(x)  # make a prediction
    ...     metric = metric.update(y, y_pred)  # update the metric
    ...     model_pipeline = model_pipeline.learn_one(x,y)  # make the model learn

    >>> print(f'Accuracy: {metric.get()}')
    Accuracy: 0.6728
    """

    def __init__(
        self,
        module: Union[torch.nn.Module, Type[torch.nn.Module]],
        loss_fn: Union[str, Callable] = "binary_cross_entropy",
        optimizer_fn: Union[str, Callable] = "sgd",
        lr: float = 1e-3,
        device: str = "cpu",
        seed: int = 42,
        **kwargs,
    ):
        self.observed_classes = []
        self.output_layer = None
        super().__init__(
            loss_fn=loss_fn,
            optimizer_fn=optimizer_fn,
            module=module,
            device=device,
            lr=lr,
            seed=seed,
            **kwargs,
        )

    @classmethod
    def _unit_test_params(cls) -> dict:
        """
        Returns a dictionary of parameters to be used for unit testing the respective class.

        Yields
        -------
        dict
            Dictionary of parameters to be used for unit testing the respective class.
        """

        class MyModule(torch.nn.Module):
            def __init__(self, n_features):
                super(MyModule, self).__init__()
                self.dense0 = torch.nn.Linear(n_features, 5)
                self.nonlin = torch.nn.ReLU()
                self.dense1 = torch.nn.Linear(5, 2)
                self.softmax = torch.nn.Softmax(dim=-1)

            def forward(self, X, **kwargs):
                X = self.nonlin(self.dense0(X))
                X = self.nonlin(self.dense1(X))
                X = self.softmax(X)
                return X

        yield {
            "module": MyModule,
            "loss_fn": "l1",
            "optimizer_fn": "sgd",
        }

    @classmethod
    def _unit_test_skips(self) -> set:
        """
        Indicates which checks to skip during unit testing.
        Most estimators pass the full test suite. However, in some cases, some estimators might not
        be able to pass certain checks.
        Returns
        -------
        set
            Set of checks to skip during unit testing.
        """
        return {
            "check_pickling",
            "check_shuffle_features_no_impact",
            "check_emerging_features",
            "check_disappearing_features",
            "check_predict_proba_one",
            "check_predict_proba_one_binary",
        }

    def learn_one(self, x: dict, y: ClfTarget, **kwargs) -> "Classifier":
        """
        Performs one step of training with a single example.

        Parameters
        ----------
        x
            Input example.
        y
            Target value.

        Returns
        -------
        Classifier
            The classifier itself.
        """
        # check if model is initialized
        if not self.module_initialized:
            self.kwargs["n_features"] = len(x)
            self.initialize_module(**self.kwargs)
        x = dict2tensor(x, device=self.device)

        # check last layer
        if y not in self.observed_classes:
            self.observed_classes.append(y)

        return self._learn(x=x, y=y)

    def _learn(self, x: torch.Tensor, y: Union[ClfTarget, List[ClfTarget]]):
        self.module.train()
        self.optimizer.zero_grad()
        y_pred = self.module(x)
        n_classes = y_pred.shape[-1]
        y = labels2onehot(
            y=y, classes=self.observed_classes, n_classes=n_classes, device=self.device
        )
        loss = self.loss_fn(y_pred, y)
        loss.backward()
        self.optimizer.step()
        return self

    def predict_proba_one(self, x: dict) -> Dict[ClfTarget, float]:
        """
        Predict the probability of each label given the input.

        Parameters
        ----------
        x
            Input example.

        Returns
        -------
        Dict[ClfTarget, float]
            Dictionary of probabilities for each label.
        """
        if not self.module_initialized:
            self.kwargs["n_features"] = len(x)
            self.initialize_module(**self.kwargs)
        x = dict2tensor(x, device=self.device)
        self.module.eval()
        y_pred = self.module(x)
        return output2proba(y_pred, self.observed_classes)

    def learn_many(self, X: pd.DataFrame, y: List) -> "Classifier":
        """
        Performs one step of training with a batch of examples.

        Parameters
        ----------
        X
            Input examples.
        y
            Target values.

        Returns
        -------
        Classifier
            The classifier itself.
        """
        # check if model is initialized
        if not self.module_initialized:
            self.kwargs["n_features"] = len(X.columns)
            self.initialize_module(**self.kwargs)
        X = df2tensor(X, device=self.device)

        # check last layer
        for y_i in y:
            if y_i not in self.observed_classes:
                self.observed_classes.append(y_i)

        y = labels2onehot(
            y,
            self.observed_classes,
            self.output_layer.out_features,
            device=self.device,
        )
        self.module.train()
        return self._learn(x=X, y=y)

    def predict_proba_many(self, X: pd.DataFrame) -> List:
        """
        Predict the probability of each label given the input.

        Parameters
        ----------
        X
            Input examples.

        Returns
        -------
        List
            List of dictionaries of probabilities for each label.
        """
        if not self.module_initialized:
            self.kwargs["n_features"] = len(X.columns)
            self.initialize_module(**self.kwargs)
        X = df2tensor(X, device=self.device)
        self.module.eval()
        y_preds = self.module(X)
        return output2proba(y_preds, self.observed_classes)


    def find_output_layer(self) -> nn.Linear:
        """Return the output layer of a network.

        Parameters
        ----------
        net
            The network to find the output layer of.

        Returns
        -------
        nn.Linear
            The output layer of the network.
        """

        for layer in list(self.module.children())[::-1]:
            if isinstance(layer, nn.Linear):
                return layer
        raise ValueError("No dense layer found.")