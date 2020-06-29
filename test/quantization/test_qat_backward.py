from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import torch
import numpy as np
import copy
from torch.quantization.fake_quantize import FakeQuantize
from torch.quantization.fake_quantize_backward import _FakeQuantizeWithBackward
from torch.testing._internal.common_utils import TestCase
from .test_workflow_module import to_tensor
from hypothesis import given
from hypothesis import strategies as st
import torch.testing._internal.hypothesis_utils as hu
hu.assert_deadline_disabled()

NP_RANDOM_SEED = 1776
tolerance = 1e-6

class TestQATBackward(TestCase):

    @given(quantize_forward=st.booleans(),
           quantize_backward=st.booleans(),
           device=st.sampled_from(['cpu']),
           X=hu.tensor(shapes=hu.array_shapes(1, 5,),
                       qparams=hu.qparams(dtypes=torch.quint8)))
    def test_forward_and_backward(self, quantize_forward, quantize_backward, device, X):

        r"""Tests the forward and backward path of the FakeQuantizeWithBackward module
        """
        def fake_quantize_tensor(X):
            scale, zero_point = torch._choose_qparams_per_tensor(X, reduce_range=False)
            return torch.fake_quantize_per_tensor_affine(X, scale, zero_point, 0, 255)

        np.random.seed(NP_RANDOM_SEED)
        X, (_, _, torch_type) = X
        quant_min = torch.iinfo(torch_type).min
        quant_max = torch.iinfo(torch_type).max

        fake_with_backward = _FakeQuantizeWithBackward(quant_min=quant_min,
                                                       quant_max=quant_max,
                                                       quantize_forward=quantize_forward,
                                                       quantize_backward=quantize_backward)

        fake_reference = FakeQuantize(quant_min=quant_min, quant_max=quant_max)

        X = to_tensor(X, device)
        X.requires_grad_()
        X_prime = copy.deepcopy(X)
        X_prime.requires_grad_()

        Y = fake_with_backward(X)
        Y_prime = fake_reference(X_prime) if quantize_forward else X_prime

        self.assertEqual(Y, Y_prime, rtol=tolerance, atol=tolerance)

        dout = torch.rand(X.shape, dtype=torch.float).to(device)

        Y.backward(dout)
        Y_prime.backward(dout)

        dX_prime = fake_quantize_tensor(X_prime.grad) if quantize_backward else X_prime.grad

        self.assertEqual(X.grad, dX_prime, rtol=tolerance, atol=tolerance)