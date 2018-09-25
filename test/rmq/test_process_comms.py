import shortuuid
from tornado import testing
import unittest

from kiwipy import rmq
import plumpy
from plumpy import process_comms, test_utils

try:
    import pika
except ImportError:
    pika = None

AWAIT_TIMEOUT = testing.get_async_test_timeout()


@unittest.skipIf(not pika, "Requires pika library and RabbitMQ")
class TestRemoteProcessController(testing.AsyncTestCase):
    def setUp(self):
        super(TestRemoteProcessController, self).setUp()

        self.loop = self.io_loop

        message_exchange = "{}.{}".format(self.__class__.__name__, shortuuid.uuid())
        task_exchange = "{}.{}".format(self.__class__.__name__, shortuuid.uuid())
        task_queue = "{}.{}".format(self.__class__.__name__, shortuuid.uuid())

        self.communicator = rmq.connect(
            connection_params={'url': 'amqp://guest:guest@localhost:5672/'},
            message_exchange=message_exchange,
            task_exchange=task_exchange,
            task_queue=task_queue,
            testing_mode=True
        )

        self.process_controller = process_comms.RemoteProcessController(self.communicator)

    def tearDown(self):
        # Close the connector before calling super because it will
        # close the loop
        self.communicator.stop()
        super(TestRemoteProcessController, self).tearDown()

    @testing.gen_test
    def test_pause(self):
        proc = test_utils.WaitForSignalProcess(communicator=self.communicator)
        # Run the process in the background
        proc.loop().add_callback(proc.step_until_terminated)
        # Send a pause message
        result = yield self.process_controller.pause_process(proc.pid)

        # Check that it all went well
        self.assertTrue(result)
        self.assertTrue(proc.paused)

    @testing.gen_test
    def test_play(self):
        proc = test_utils.WaitForSignalProcess(communicator=self.communicator)
        # Run the process in the background
        proc.loop().add_callback(proc.step_until_terminated)
        self.assertTrue(proc.pause())

        # Send a play message
        result = yield self.process_controller.play_process(proc.pid)

        # Check that all is as we expect
        self.assertTrue(result)
        self.assertEqual(proc.state, plumpy.ProcessState.WAITING)

    @testing.gen_test
    def test_kill(self):
        proc = test_utils.WaitForSignalProcess(communicator=self.communicator)
        # Run the process in the event loop
        self.loop.add_callback(proc.step_until_terminated)

        # Send a kill message and wait for it to be done
        result = yield self.process_controller.kill_process(proc.pid)

        # Check the outcome
        self.assertTrue(result)
        self.assertEqual(proc.state, plumpy.ProcessState.KILLED)

    @testing.gen_test
    def test_status(self):
        proc = test_utils.WaitForSignalProcess(communicator=self.communicator)
        # Run the process in the background
        proc.loop().add_callback(proc.step_until_terminated)

        # Send a status message
        status = yield self.process_controller.get_status(proc.pid)

        self.assertIsNotNone(status)

    def test_broadcast(self):
        messages = []

        def on_broadcast_receive(**msg):
            messages.append(msg)

        self.communicator.add_broadcast_subscriber(on_broadcast_receive)
        proc = test_utils.DummyProcess(loop=self.loop, communicator=self.communicator)
        proc.execute()

        expected_subjects = []
        for i, state in enumerate(test_utils.DummyProcess.EXPECTED_STATE_SEQUENCE):
            from_state = test_utils.DummyProcess.EXPECTED_STATE_SEQUENCE[i - 1].value if i != 0 else None
            expected_subjects.append(
                "state_changed.{}.{}".format(from_state, state.value))

        for i, message in enumerate(messages):
            self.assertEqual(message['subject'], expected_subjects[i])



@unittest.skipIf(not pika, "Requires pika library and RabbitMQ")
class TestRemoteProcessThreadController(testing.AsyncTestCase):
    def setUp(self):
        super(TestRemoteProcessThreadController, self).setUp()

        self.loop = self.io_loop

        message_exchange = "{}.{}".format(self.__class__.__name__, shortuuid.uuid())
        task_exchange = "{}.{}".format(self.__class__.__name__, shortuuid.uuid())
        task_queue = "{}.{}".format(self.__class__.__name__, shortuuid.uuid())

        self.communicator = rmq.connect(
            connection_params={'url': 'amqp://guest:guest@localhost:5672/'},
            message_exchange=message_exchange,
            task_exchange=task_exchange,
            task_queue=task_queue,
            testing_mode=True
        )

        self.process_controller = process_comms.RemoteProcessThreadController(self.communicator)

    def tearDown(self):
        # Close the connector before calling super because it will
        # close the loop
        self.communicator.stop()
        super(TestRemoteProcessThreadController, self).tearDown()

    @testing.gen_test
    def test_pause(self):
        proc = test_utils.WaitForSignalProcess(communicator=self.communicator)
        # Send a pause message
        pause_future = self.process_controller.pause_process(proc.pid)
        # Let the process respond to the request
        yield
        result = pause_future.result(timeout=AWAIT_TIMEOUT)

        # Check that it all went well
        self.assertTrue(result)
        self.assertTrue(proc.paused)

    @testing.gen_test
    def test_play(self):
        proc = test_utils.WaitForSignalProcess(communicator=self.communicator)
        self.assertTrue(proc.pause())

        # Send a play message
        play_future = self.process_controller.pause_process(proc.pid)
        yield
        # Allow the process to respond to the request
        result = play_future.result(timeout=AWAIT_TIMEOUT)

        # Check that all is as we expect
        self.assertTrue(result)
        self.assertEqual(proc.state, plumpy.ProcessState.CREATED)

    @testing.gen_test
    def test_kill(self):
        proc = test_utils.WaitForSignalProcess(communicator=self.communicator)

        # Send a play message
        kill_future = self.process_controller.kill_process(proc.pid)
        yield
        # Allow the process to respond to the request
        result = kill_future.result(timeout=AWAIT_TIMEOUT)

        # Check the outcome
        self.assertTrue(result)
        self.assertEqual(proc.state, plumpy.ProcessState.KILLED)

    @testing.gen_test
    def test_status(self):
        proc = test_utils.WaitForSignalProcess(communicator=self.communicator)
        # Run the process in the background
        proc.loop().add_callback(proc.step_until_terminated)

        # Send a status message
        status_future = self.process_controller.get_status(proc.pid)
        # Let the process respond
        yield
        status = status_future.result(timeout=AWAIT_TIMEOUT)

        self.assertIsNotNone(status)
