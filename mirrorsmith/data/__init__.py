"""Data ingestion foundation.

Everything the rest of mirrorsmith knows about Path of Exile enters through this
package. Downstream code depends only on the normalized models here (e.g.
``mirrorsmith.data.tree.PassiveTree``) — never on a third party's raw file
layout — so when an upstream source restructures, we fix one adapter, not the
whole tool.
"""
