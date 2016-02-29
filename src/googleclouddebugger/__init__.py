# Copyright 2015 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS-IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Main module for Python Cloud Debugger.

The debugger is enabled in a very similar way to enabling pdb.

The debugger becomes the main module. It eats up its arguments until it gets
to argument '--' that serves as a separator between debugger arguments and
the application command line. It then attaches the debugger and runs the
actual app.
"""

import logging
import os
import sys

import appengine_pretty_printers
import breakpoints_manager
import capture_collector
import cdbg_native
import gcp_hub_client

# Versioning scheme: MAJOR.MINOR
# The major version should only change on breaking changes. Minor version
# changes go between regular updates. Instances running debuggers with
# different major versions will show up as two different debuggees.
__version__ = '1.7'

_flags = None


def _StartDebugger():
  global _hub_client
  global _breakpoints_manager

  cdbg_native.InitializeModule(_flags)

  _hub_client = gcp_hub_client.GcpHubClient()
  _breakpoints_manager = breakpoints_manager.BreakpointsManager(_hub_client)

  # Set up loggers for logpoints. App Engine will capture normal logging
  # using a special log handler that it adds to the default logger during
  # initialization.
  capture_collector.log_info_message = logging.info
  capture_collector.log_warning_message = logging.warning
  capture_collector.log_error_message = logging.error

  """Configures and starts the debugger."""
  capture_collector.CaptureCollector.pretty_printers.append(
      appengine_pretty_printers.PrettyPrinter)

  _hub_client.on_active_breakpoints_changed = (
      _breakpoints_manager.SetActiveBreakpoints)
  _hub_client.on_idle = _breakpoints_manager.CheckBreakpointsExpiration
  if _flags.get('enable_service_account_auth') in ('1', 'true', True):
    _hub_client.EnableServiceAccountAuth(
        _flags['project_id'],
        _flags['project_number'],
        _flags['service_account_email'],
        _flags['service_account_p12_file'])
  else:
    _hub_client.EnableGceAuth()
  _hub_client.InitializeDebuggeeLabels(_flags)
  _hub_client.Start()


def _DebuggerMain():
  """Starts the debugger and runs the application with debugger attached."""
  global _flags

  # The first argument is cdbg module, which we don't care.
  del sys.argv[0]

  # Parse debugger flags until we encounter '--'.
  _flags = {}
  while sys.argv[0]:
    arg = sys.argv[0]
    del sys.argv[0]

    if arg == '--':
      break

    (name, value) = arg.strip('-').split('=', 2)
    _flags[name] = value

  _StartDebugger()

  # Run the app. The following code was mostly copied from pdb.py.
  app_path = sys.argv[0]

  sys.path[0] = os.path.dirname(app_path)

  import __main__  # pylint: disable=g-import-not-at-top
  __main__.__dict__.clear()
  __main__.__dict__.update({'__name__': '__main__',
                            '__file__': app_path,
                            '__builtins__': __builtins__})
  locals = globals = __main__.__dict__  # pylint: disable=redefined-builtin

  sys.modules['__main__'] = __main__

  exec 'execfile(%r)' % app_path in globals, locals  # pylint: disable=exec-used


def AttachDebugger(**kwargs):
  """Starts the debugger for already running application.

  This function should only be called once.

  Args:
    flags: debugger configuration.

  Raises:
    RuntimeError: if called more than once.
    ValueError: if flags is not a valid dictionary.
  """
  global _flags

  if _flags is not None:
    raise RuntimeError('Debugger already attached')

  _flags = kwargs
  _StartDebugger()

