CLI 参考
========

``unified-icc server`` 命令管理 Unified ICC API 服务器的生命周期。

实现位于 ``unified_icc.cli.server_cmd``。

.. code-block:: bash

   unified-icc server start [--host HOST] [--port PORT] [-d/--detach]
   unified-icc server stop
   unified-icc server status

start
------

启动 API 服务器。

.. code-block:: bash

   unified-icc server start --host 0.0.0.0 --port 8900 --detach

.. list-table::
   :header-rows: 1
   :widths: 25 15 60

   * - 参数
     - 默认值
     - 说明
   * - ``--host``
     - ``0.0.0.0``
     - 服务器绑定地址
   * - ``--port``, ``-p``
     - ``8900``
     - 服务器绑定端口
   * - ``--detach``, ``-d``
     - ``false``
     - fork 到后台运行

行为
~~~~

1. 检查 ``~/.unified-icc/server.pid`` 是否存在且 PID 存活；若存活则退出
2. 若指定 ``--detach``: 调用 ``os.fork()``，子进程调用 ``os.setsid()`` 脱离终端，重定向 stdin/stdout/stderr 到 /dev/null，然后启动服务器
3. 若前台运行: 直接在当前进程启动服务器，KeyboardInterrupt（Ctrl+C）优雅退出
4. 启动时将 PID 写入 ``~/.unified-icc/server.pid``
5. 服务器退出（任意原因）后自动删除 PID 文件

stop
-----

停止运行中的 API 服务器。

.. code-block:: bash

   unified-icc server stop

行为
~~~~

1. 读取 ``~/.unified-icc/server.pid`` 获取 PID
2. 发送 ``SIGTERM``
3. 等待最多 5 秒（每 0.1 秒检查一次）
4. 若仍未退出，发送 ``SIGKILL`` 强制终止
5. 删除 PID 文件

若服务器未运行，输出提示信息并以 0 退出。

status
-------

查看 API 服务器运行状态。

.. code-block:: bash

   unified-icc server status

输出示例（running）:

.. code-block:: text

   API Server Status
   =================
     Status    running
     PID       12345
     PID file  /home/user/.unified-icc/server.pid

输出示例（stopped）:

.. code-block:: text

   API Server Status
   =================
     Status    stopped
     Stale PID  12345

**Status 列**:

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - 状态
     - 含义
   * - ``running``
     - 服务器正在运行（PID 文件存在且进程存活）
   * - ``stopped``
     - 服务器未运行（无 PID 文件或进程不存活）
