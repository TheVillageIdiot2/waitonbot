# Use if we want to await tasks one by one
# Hint: We usually don't
SINGLE_THREAD_TASKS = False


# If we were interested in performance, this should probably be turned off. However, it's fairly harmless and
# for the most part pretty beneficial to us.
# See https://docs.python.org/3/library/asyncio-dev.html#asyncio-debug-mode
# Note that this occasionally will give us warnings if SINGLE_THREAD_TAKS is False (which it usually is)
# howver, these warnings are harmless, as regardless of if aa task is awaited it still does its job
USE_ASYNC_DEBUG_MODE = False
