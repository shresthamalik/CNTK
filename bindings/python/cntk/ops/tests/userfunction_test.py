# Copyright (c) Microsoft. All rights reserved.
# Licensed under the MIT license. See LICENSE.md file in the project root
# for full license information.
# ==============================================================================

"""
Unit tests for function extension
"""

from __future__ import division, print_function
import numpy as np
import pytest
import cntk as C

from cntk.ops.functions import Function, UserFunction
from .ops_test_utils import AA


class MyPlus(UserFunction):
    def __init__(self, arg1, arg2, name='f1'):
        super(MyPlus, self).__init__([arg1, arg2], name=name)

        self.forward_calls = 0
        self.backward_calls = 0

    def infer_outputs(self):
        return [C.output_variable(self.inputs[0].shape,
                                  self.inputs[0].dtype,
                                  self.inputs[0].dynamic_axes)]

    def forward(self, arguments, device=None, outputs_to_retain=None):
        assert len(self.inputs) == 2

        result = arguments[0] + arguments[1]

        self.forward_calls += 1

        return None, result

    def backward(self, state, root_gradients, input_gradients):
        self.backward_calls += 1

        for input in input_gradients:
            input_gradients[input] = root_gradients

    def serialize(self):
        return {'forward_calls': self.forward_calls,
                'backward_calls': self.backward_calls}

    @staticmethod
    def deserialize(inputs, name, state):
        f = MyPlus(inputs[0], inputs[1], name)
        f.forward_calls = state['forward_calls']
        f.backward_calls = state['backward_calls']
        return f


class MyPlusPlus(MyPlus):
    def __init__(self, inputs, name, state={}):
        super(MyPlusPlus, self).__init__(inputs[0], inputs[1], name=name + name)

    def forward(self, *args, **kwargs):
        r1 = super(MyPlusPlus, self).forward(*args, **kwargs)
        r2 = super(MyPlusPlus, self).forward(*args, **kwargs)
        return None, r1[1] + r2[1]

    def serialize(self):
        return None

    @staticmethod
    def deserialize(*args):
        return MyPlusPlus(*args)


def test_ext_eval_1():
    dim = 4
    p = C.parameter(shape=(dim,), init=10, name='p')
    i = C.sequence.input_variable(dim, needs_gradient=True, name='i_var')
    m = C.user_function(MyPlus(i, C.constant(3)))
    z = m + p

    input_data = np.random.rand(dim)
    result = z.eval([input_data])
    assert np.allclose(result[0][0], input_data + 3 + 10)


def test_ext_eval_freedimension_input():
    i = C.sequence.input_variable((C.FreeDimension), needs_gradient=True, name='i_var')
    m = C.user_function(MyPlus(i, C.constant(3)))

    input_data = np.random.rand(3)
    gradient_value, result = m.grad({i: input_data}, wrt=[i], outputs=[m.output])
    assert np.allclose(result[0][0], input_data + 3)
    assert np.allclose(gradient_value[0][0], np.ones_like(input_data))

    input_data = np.random.rand(6)
    gradient_value, result = m.grad({i: input_data}, wrt=[i], outputs=[m.output])
    assert np.allclose(result[0][0], input_data + 3)
    assert np.allclose(gradient_value[0][0], np.ones_like(input_data))


def test_ext_eval_2_only_param():
    dim = 4
    p = C.parameter(shape=(dim,), init=10, name='p')
    i = C.sequence.input_variable(dim, needs_gradient=True, name='i_var')
    m = C.user_function(MyPlus(p, C.constant(3)))
    # combine does not work
    # z = combine([m.output])
    z = m + i

    input_data = np.random.rand(dim)
    result = z.eval([input_data])
    assert np.allclose(result[0][0], input_data + 3 + 10)


def test_ext_eval_3_no_input():
    dim = 4
    p = C.parameter(shape=(dim,), init=10, name='p')
    m = C.user_function(MyPlus(p, C.constant(3)))
    z = m + 0

    result = z.eval()
    # No batch dimension since we have no input
    assert np.allclose(result, np.zeros_like(p) + 10 + 3)


def test_ext_eval_4_a_inside_graph():
    dim = 4
    p_init = 10
    p = C.parameter(shape=(dim,), init=p_init, name='p')
    m = C.user_function(MyPlus(p, C.constant(3)))
    z = p * m

    result = z.eval()
    # No batch dimension since we have no input
    assert np.allclose(result, ((p_init * np.ones_like(result)) + 3) * p_init)


def test_ext_eval_4_b_inside_graph():
    dim = 4
    p_init = 10
    p = C.parameter(shape=(dim,), init=p_init, name='p')
    z = C.user_function(p * MyPlus(p, C.constant(3)))

    result = z.eval()
    # No batch dimension since we have no input
    assert np.allclose(result, ((p_init * np.ones_like(result)) + 3) * p_init)


def test_ext_eval_5_times():
    dim = 2
    p_init = 10
    p = C.parameter(shape=(dim,), init=p_init, name='p')
    m = C.user_function(MyPlus(p, C.constant(3)))
    z = C.times(m, C.parameter(shape=(2, 50), init=2))

    result = z.eval()
    # No batch dimension since we have no input
    assert np.allclose(result, ((p_init * np.ones_like(result)) + 3) * 2 * 2)


def test_ext_eval_6_clone():
    dim = 4
    i = C.sequence.input_variable(dim, needs_gradient=True, name='i_var')
    m = i + 3

    p = C.parameter(shape=(dim,), init=10, name='p')
    z = m + p

    m_udf = C.user_function(MyPlus(i, C.constant(3)))
    z_clone = z.clone('share', {m: m_udf})

    input_data = np.random.rand(dim)
    result = z_clone.eval([input_data])
    assert np.allclose(result[0][0], input_data + 3 + 10)


def test_ext_eval_7_placeholder():
    dim = 4
    p = C.parameter(shape=(dim,), init=10, name='p')
    i = C.sequence.input_variable(dim, needs_gradient=True, name='i_var')
    pl = C.placeholder()
    m = C.user_function(MyPlus(pl, C.constant(3)))
    z = m + p
    z.replace_placeholder(i)

    input_data = np.random.rand(dim)
    result = z.eval([input_data])
    assert np.allclose(result[0][0], input_data + 3 + 10)


def test_ext_train(tmpdir):
    dim = 4

    p = C.parameter(shape=(dim,), init=10)
    i = C.sequence.input_variable(dim, needs_gradient=True, name='i_var')
    m = MyPlus(i, C.constant(3), 'my_plus')
    # keeping m unwrapped since we need to access its member variables
    z = C.user_function(m) + p

    momentum_time_constant = C.momentum_as_time_constant_schedule(1100)
    lr_per_sample = C.learning_rate_schedule(0.007, C.UnitType.sample)
    trainer = C.Trainer(z, (z + 0, z + 0),
                        [C.momentum_sgd(z.parameters, lr_per_sample, momentum_time_constant,
                                        True)])

    i = 0
    while i < 100:
        i += 1
        input_data = np.random.rand(dim)
        trainer.train_minibatch([input_data])

    assert m.forward_calls == m.backward_calls == 100

    filepath = str(tmpdir / 'test_ext_train.dat')

    z.save(filepath)

    buf = open(filepath, 'rb').read()

    # this is only need for Python 2.7
    # (which does not distinguish between bytes and strings)
    if isinstance(buf, str):
        buf = bytearray(buf)

    z1 = Function.load(buf)

    m1 = z1.find_by_name('my_plus')
    # m1 is an instance of UserFunction, cannot directly downcast it to MyPlus,
    # using serialize as workaround:
    state = m1.serialize()['state']

    assert state['forward_calls'] == state['backward_calls'] == 100


def test_udf_clone():
    dim = 4
    i = C.sequence.input_variable(dim, needs_gradient=True, name='i_var')
    m_udf = C.user_function(MyPlus(i, C.constant(3)))
    p = C.parameter(shape=(dim,), init=10, name='p')
    z = m_udf + p

    z_clone = z.clone('share')

    input_data = np.random.rand(dim)
    result = z_clone.eval([input_data])
    assert np.allclose(result[0][0], input_data + 3 + 10)


@pytest.mark.parametrize("payload", [(np.asarray([[[1, 2, 3.0]]]),),
                                     (77,),
                                     ("a", 2),
                                     (),
                                     (None)])
def test_ext_backpropstate(payload):

    class TestBackPropState(UserFunction):
        def __init__(self, arg, payload, name='f1'):
            self.payload = payload
            super(TestBackPropState, self).__init__([arg])

        def infer_outputs(self):
            return [C.output_variable(self.inputs[0].shape, self.inputs[0].dtype, self.inputs[0].dynamic_axes)]

        def forward(self, argument, device=None, outputs_to_retain=None):
            return self.payload, argument

        def backward(self, state, root_gradients):
            assert state == self.payload
            return root_gradients

    dim = 4

    p = C.parameter(shape=(dim,), init=10)
    in1 = C.input_variable(dim, needs_gradient=True, name='i_var')
    m = C.user_function(TestBackPropState(in1, payload))
    z = m + p

    lr_per_sample = C.learning_rate_schedule(0.007, C.UnitType.sample)
    trainer = C.Trainer(None, (z), [C.sgd(z.parameters, lr_per_sample)])

    for i in range(100):
        input_data = np.random.rand(dim)
        trainer.train_minibatch({in1: [input_data]})


class LambdaFunc(UserFunction):
    def __init__(self,
                 arg,
                 when=lambda arg: True,
                 execute=lambda arg: print(arg),
                 name=''):
        self.when = when
        self.execute = execute
        arg = arg if isinstance(arg, list) else [arg]
        super(LambdaFunc, self).__init__(arg, name=name)

    @property
    def op_name(self):
        return 'conditional_exec_lambda'

    def infer_outputs(self):
        return [C.output_variable(self.inputs[0].shape, self.inputs[0].dtype, self.inputs[0].dynamic_axes)]

    def forward(self, argument, device=None, outputs_to_retain=None):
        if self.when(argument):
            self.execute(argument)

        return None, argument

    def backward(self, state, root_gradients):
        return root_gradients


def test_ext_lambdafunc(tmpdir):
    dim = 4

    class CallbackCounter(object):
        def __init__(self):
            self.count = 0

        def inc(self, arg):
            self.count += 1

    cb = CallbackCounter()

    p = C.parameter(shape=(dim,), init=1)
    i = C.input_variable(dim, needs_gradient=True, name='i_var')
    k = i * p
    m = LambdaFunc(k,
                   when=lambda arg: np.sum(arg) > 1,
                   execute=cb.inc)
    m = C.user_function(m)
    z0 = m + 0

    filepath = str(tmpdir / 'test_ext_lambdafunc.dat')
    z0.save(filepath)

    Function.register_udf_deserialize_callback('conditional_exec_lambda',
                                               lambda x, *unused: LambdaFunc(x, when=lambda arg: np.sum(arg) > 1, execute=cb.inc))

    z = Function.load(filepath)

    momentum_time_constant = C.momentum_as_time_constant_schedule(1100)
    lr_per_sample = C.learning_rate_schedule(0.007, C.UnitType.sample)
    trainer = C.Trainer(z, (z + 0, z + 0), [C.momentum_sgd(z.parameters,
                                                           lr_per_sample,
                                                           momentum_time_constant,
                                                           True)])

    i = 0
    input_data = 0.1 * np.ones(dim)
    trainer.train_minibatch([input_data])
    assert cb.count == 0

    input_data = 0.3 * np.ones(dim)
    trainer.train_minibatch([input_data])
    assert cb.count == 1


class PlusAndLast(UserFunction):
    impl_func = None

    def __init__(self, arg1, arg2, name='f1'):
        i1 = C.input_variable(arg1.shape, arg1.dtype, name='i1', dynamic_axes=arg1.dynamic_axes)
        i2 = C.input_variable(arg2.shape, arg2.dtype, name='i2', dynamic_axes=arg2.dynamic_axes)
        self.impl_func = C.sequence.last(i1 + C.sequence.broadcast_as(i2, i1))

        super(PlusAndLast, self).__init__([arg1, arg2], name=name)

    def infer_outputs(self):
        impl_func_output = self.impl_func.output
        return [C.output_variable(impl_func_output.shape, impl_func_output.dtype, impl_func_output.dynamic_axes)]

    def forward(self, arguments, device=None, outputs_to_retain=None):
        _, result = self.impl_func.forward({self.impl_func.arguments[0]: arguments[0], self.impl_func.arguments[1]: arguments[1]}, [self.impl_func.output])
        return None, result[self.impl_func.output]


def test_udf_plus_and_last():
    x = C.sequence.input_variable(shape=(2,))
    y = C.input_variable(shape=(2,))

    func = C.user_function(PlusAndLast(x, y))

    dt_precision = np.float32
    operand1 = [AA([[1., 2.], [3., 4.]], dtype=dt_precision)]
    operand2 = [AA([2., 2.], dtype=dt_precision)]

    _, result = func.forward({x: operand1, y: operand2}, [func.output])

    expected_forward = AA([[[5., 6.]]], dtype=dt_precision)
    assert np.allclose(result[func.output], expected_forward)


class MultiOutputUserFunction(UserFunction):
    def __init__(self, arg1, arg2, name='f1'):
        super(MultiOutputUserFunction, self).__init__([arg1, arg2], name=name)

    def infer_outputs(self):
        return [C.output_variable(self.inputs[0].shape, self.inputs[0].dtype, self.inputs[0].dynamic_axes),
                C.output_variable(self.inputs[0].shape, self.inputs[0].dtype, self.inputs[0].dynamic_axes)]

    def forward(self, arguments, outputs, device=None, outputs_to_retain=None):
        assert len(self.inputs) == 2

        outputs[self.outputs[0]] = [a0 + 2 * a1 for a0, a1 in zip(*arguments)]
        outputs[self.outputs[1]] = [2 * a0 + a1 for a0, a1 in zip(*arguments)]

        return None

    def backward(self, state, root_gradients, variables):
        if self.inputs[0] in variables:
            variables[self.inputs[0]] = [r0 + 2 * r1 for r0, r1 in zip(root_gradients[self.outputs[0]], root_gradients[self.outputs[1]])]

        if self.inputs[1] in variables:
            variables[self.inputs[1]] = [2 * r0 + r1 for r0, r1 in zip(root_gradients[self.outputs[0]], root_gradients[self.outputs[1]])]


def test_multioutput_udf():
    dim = 2
    x = C.sequence.input_variable(dim, needs_gradient=True, name='x')
    y = C.sequence.input_variable(dim, needs_gradient=True, name='y')
    op = C.user_function(MultiOutputUserFunction(x, y))

    x_data = [AA([[1., 2.], [3., 4.]], dtype=np.float32)]
    y_data = [AA([[5., 6.], [7., 8.]], dtype=np.float32)]
    result = op.eval({x: x_data, y: y_data})
    assert np.allclose(result[op.outputs[0]], x_data[0] + 2 * y_data[0])
    assert np.allclose(result[op.outputs[1]], 2 * x_data[0] + y_data[0])

    op = op.outputs[0] + op.outputs[1]
    gradients = op.grad({x: x_data, y: y_data}, op.arguments)
    assert np.allclose(gradients[op.arguments[0]], [[[3., 3.], [3., 3.]]])
    assert np.allclose(gradients[op.arguments[1]], [[[3., 3.], [3., 3.]]])


def test_udf_op_name():
    dim = 4
    i = C.input_variable(dim, needs_gradient=True, name='i_var')
    m = C.user_function(MyPlus(i, C.constant(3)))
    assert str(m.root_function) != ''


class MyPlusWithNoGradientToRightOperand(UserFunction):
    def __init__(self, arg1, arg2, name='f1'):
        super(MyPlusWithNoGradientToRightOperand, self).__init__([arg1, arg2], name=name)

    def infer_outputs(self):
        return [C.output_variable(self.inputs[0].shape, self.inputs[0].dtype, self.inputs[0].dynamic_axes)]

    def forward(self, arguments, device=None, outputs_to_retain=None):
        assert len(self.inputs) == 2

        result = [a0 + a1 for a0, a1 in zip(*arguments)]

        return None, result

    def backward(self, state, root_gradients, input_gradients):
        input_gradients[self.inputs[0]] = root_gradients


def test_udf_no_gradient_for_some_inputs():
    dim = 2
    x = C.sequence.input_variable(dim, needs_gradient=True, name='x')
    y = C.sequence.input_variable(dim, needs_gradient=True, name='y')
    op = C.user_function(MyPlusWithNoGradientToRightOperand(x, y))

    x_data = [AA([[1., 2.], [3., 4.]], dtype=np.float32)]
    y_data = [AA([[5., 6.], [7., 8.]], dtype=np.float32)]
    gradients, result = op.grad({x: x_data, y: y_data}, op.arguments, [op.output])

    assert np.allclose(gradients[op.arguments[0]], [[[1., 1.], [1., 1.]]])
    assert np.allclose(gradients[op.arguments[1]], [[[0., 0.], [0., 0.]]])

    assert np.allclose(result, [[[6., 8.], [10., 12.]]])


class MyPlusWithNoGradientNeededForOutput(UserFunction):
    def __init__(self, arg1, arg2, name='f1'):
        super(MyPlusWithNoGradientNeededForOutput, self).__init__([arg1, arg2], name=name)

    def infer_outputs(self):
        return [C.output_variable(self.inputs[0].shape, self.inputs[0].dtype, self.inputs[0].dynamic_axes, needs_gradient=False)]

    def forward(self, arguments, device=None, outputs_to_retain=None):
        assert len(self.inputs) == 2

        result = [a0 + a1 for a0, a1 in zip(*arguments)]

        return None, result

    def backward(self, state, root_gradients, input_gradients):
        raise ValueError("MyPlusWithNoGradientNeededForOutput does not need gradient for output and backward must not be called")


def test_udf_output_needs_no_gradient():
    dim = 2
    x = C.sequence.input_variable(dim, needs_gradient=True, name='x')
    y = C.sequence.input_variable(dim, needs_gradient=True, name='y')
    op = C.user_function(MyPlusWithNoGradientNeededForOutput(x, y))

    x_data = [AA([[1., 2.], [3., 4.]], dtype=np.float32)]
    y_data = [AA([[5., 6.], [7., 8.]], dtype=np.float32)]

    gradients, result = op.grad({x: x_data, y: y_data}, op.arguments, [op.output])

    assert np.allclose(gradients[op.arguments[0]], [[[0., 0.], [0., 0.]]])
    assert np.allclose(gradients[op.arguments[1]], [[[0., 0.], [0., 0.]]])

    assert np.allclose(result, [[[6., 8.], [10., 12.]]])


def test_native_user_function(tmpdir):

    if not C.cntk_py.is_native_user_function_registered('NativeUserTimesOp'):
        C.ops.register_native_user_function('NativeUserTimesOp', 'Cntk.ExtensibilityExamples-' + C.__version__.rstrip('+'), 'CreateUserTimesFunction')

    dev = C.cpu()
    x = C.input_variable((2))
    w = C.parameter((2, 2), init=np.asarray([[0.5, 2], [-0.5, 1.5]], dtype=np.float32), device=dev)
    attributes = {'param_rank': 2,
                  'padding': True,
                  'none': None,
                  'nested lists': [[1, 2, 3], [4, 5, 6]],
                  'string': 'string',
                  'some data': np.arange(1, 10, dtype=np.float32).reshape((3, 3))
                  }

    def verify_attributes(udf):
        for k, v in attributes.items():
            if not isinstance(v, np.ndarray):
                assert udf.attributes[k] == v
            else:
                assert (udf.attributes[k] == v).all()

    op = C.ops.native_user_function('NativeUserTimesOp', [w, x], attributes, 'native_user_times_function')

    verify_attributes(op.owner)

    filepath = str(tmpdir / 'test_native_user_function.dat')
    op.save(filepath)

    op_reloaded = Function.load(filepath, device=dev)
    x_data = C.NDArrayView.from_dense(np.asarray([[0.1, 0.2], [-0.1, 0.3]], dtype=np.float32), device=dev)
    result = op_reloaded.eval({op_reloaded.arguments[0]: x_data}, device=dev)

    assert np.allclose(result, [[-0.05, 0.5], [-0.2, 0.25]])

    native_times_primitive = op_reloaded.find_by_name('native_user_times_function')

    verify_attributes(native_times_primitive)


def build_test_function():
    dev = C.cpu()
    w_value = np.asarray([[0.5, 2], [-0.5, 1.5]]).astype(np.float32)
    c1_value = 2.718
    c2_value = -3.141

    if not C.cntk_py.is_native_user_function_registered('NativeUserTimesOp'):
        C.ops.register_native_user_function('NativeUserTimesOp', 'Cntk.ExtensibilityExamples-' + C.__version__.rstrip('+'), 'CreateUserTimesFunction')

    x = C.input_variable((2))

    w = C.parameter((2, 2), init=w_value, device=dev)

    op = C.user_function(MyPlus(x, C.constant(c1_value)))
    op = C.ops.native_user_function('NativeUserTimesOp', [w, op], user_function_instance_name='my_times')

    return dev, w_value, c1_value, c2_value, C.user_function(MyPlus(op, C.constant(c2_value)))


def test_both_flavors_of_user_functions(tmpdir):
    dev, w_value, c1_value, c2_value, op = build_test_function()

    filepath = str(tmpdir / 'test_native_user_function.dat')
    op.save(filepath)
    op_reloaded = Function.load(filepath, device=dev)

    np.random.seed(1)

    for i in range(5):
        x_value = np.random.random((2, 2)).astype(np.float32)
        x_data = C.NDArrayView.from_dense(x_value, device=dev)
        result = op_reloaded.eval({op_reloaded.arguments[0]: x_data}, device=dev)
        expected = np.matmul((x_value + c1_value), w_value) + c2_value
        assert np.allclose(result, expected)


def test_udf_checkpointing(tmpdir):
    dev, w_value, c1_value, c2_value, op = build_test_function()

    label = C.constant(np.asarray([[1, 2], [3, 4]]).astype(np.float32))

    loss = C.cross_entropy_with_softmax(op, label)
    eval_error = C.classification_error(op, label)

    lr_schedule = C.learning_rate_schedule(0.5, C.UnitType.minibatch)
    learner = C.sgd(op.parameters, lr_schedule)
    trainer = C.Trainer(op, (loss, eval_error), [learner])

    trainer.train_minibatch({op.arguments[0]: np.random.random((2, 2)).astype(np.float32)}, device=dev)

    filepath = str(tmpdir / 'test_checkpointing.out')

    trainer.save_checkpoint(filepath, external_state={'test': 'test'})

    d = C.cntk_py.Dictionary.load(filepath)
    assert len(d.keys()) != 0


def test_override_deserialize(tmpdir):
    dev, w_value, c1_value, c2_value, op = build_test_function()

    filepath = str(tmpdir / 'test_override_deserialize.dat')
    op.save(filepath)

    Function.register_udf_deserialize_callback(MyPlus._op_name(),
                                               lambda *x: MyPlusPlus(*x))

    op_reloaded = Function.load(filepath, device=dev)

    np.random.seed(1)

    for i in range(5):
        x_value = np.random.random((2, 2)).astype(np.float32)
        x_data = C.NDArrayView.from_dense(x_value, device=dev)
        result = op_reloaded.eval({op_reloaded.arguments[0]: x_data}, device=dev)
        expected = 2 * (np.matmul(2 * (x_value + c1_value), w_value) + c2_value)
        assert np.allclose(result, expected)


def test_override_serialize(tmpdir):
    dev = C.cpu()
    a, b = 1.2322341, -0.29084
    op = MyPlusPlus([C.constant(a), C.constant(b)], '++')
    op = MyPlusPlus([op, op], '+++')
    op = MyPlusPlus([op, op], '++++')
    op = C.user_function(op)
    result1 = op.eval({}, device=dev)

    filepath = str(tmpdir / 'test_udf_with_renamed_deserialize.dat')
    op.save(filepath)

    op_reloaded = Function.load(filepath, device=dev)

    assert result1 == op_reloaded.eval({}, device=dev)


class MyArgumentPreservingPlus(UserFunction):
    def __init__(self, arg1, arg2, name='f1'):
        super(MyArgumentPreservingPlus, self).__init__([arg1, arg2], as_numpy=False, name=name)
        self.compute_func = C.input_variable(1) + C.input_variable(1)

    def infer_outputs(self):
        return [C.output_variable(self.inputs[0].shape, self.inputs[0].dtype, self.inputs[0].dynamic_axes)]

    def forward(self, arguments, device=None, outputs_to_retain=None):
        result = self.compute_func.eval({self.compute_func.arguments[0] : arguments[0], self.compute_func.arguments[1] : arguments[1]}, as_numpy=False)
        self.backprop_state = arguments
        return self.backprop_state, result

    def backward(self, state, root_gradients, variables):
        assert state == self.backprop_state
        variables[self.inputs[0]] = root_gradients

def test_udf_input_values_no_sharing():
    i = C.input_variable(1, needs_gradient=True, name='i_var')
    m = C.user_function(MyArgumentPreservingPlus(i + 1, i + 2))
    
    w = C.parameter(shape=(1,), init=1)
    m = m + w
    m2 = C.splice(m, m, axis=0)
    m3 = C.splice(m2, m2, axis=0)
    m4 = C.splice(m3, m3, axis=0)

    grad_value, result = m4.grad({i : np.asarray([2], dtype=np.float32)}, outputs=[m4], wrt=[w, i])
    assert np.array_equal(result, [[8,  8,  8,  8,  8,  8,  8,  8]])
