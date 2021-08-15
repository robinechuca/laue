#!/usr/bin/env python3

"""
** Interface d'aide a pickle. **
--------------------------------

Fournis des interfaces aux objets de base constituants
une experience de sorte a ce que pickle puisse
les serialiser rapidement et efficacement, en selectionant seulement
l'information utile.
"""

import collections
import os


__pdoc__ = {"SpotPickelable.__getstate__": True,
            "SpotPickelable.__setstate__": True,
            "ZoneAxisPickleable.__getstate__": True,
            "ZoneAxisPickleable.__setstate__": True,
            "DiagramPickleable.__getstate__": True,
            "DiagramPickleable.__setstate__": True}


class SpotPickleable:
    """
    ** Interface pour serialiser les spots. **
    """
    def __getstate__(self):
        """
        ** Extrait le contenu d'un spot. **

        Enregistre l'etat courant, ne fait pas de zele.

        Examples
        --------
        >>> import laue
        >>> image = "laue/examples/ge_blanc.mccd"
        >>> spot = laue.Experiment(image)[0][0]
        >>> spot.__getstate__()
        {'bbox': (1368, 1873, 6, 5), 'spot_im': array([[  8,  10,  16,  16,   8,   5],
               [ 11,  17,  67,  76,  13,   9],
               [  7,  19, 184, 229,  14,   6],
               [  9,   6,  12,  19,   8,   4],
               [  5,   3,   3,   9,  14,   7]], dtype=uint16), 'dis': 0.8471580534997302, 'id': 0}
        >>>
        """
        state = {}
        state["bbox"] = self.get_bbox()
        state["im"] = self.get_image()
        state["dis"] = self.get_distortion()
        state["id"] = self.get_id()
        if self.hkl is not None:
            state["hkl"] = self.hkl
        return state

    def __setstate__(self, state):
        """
        ** Initialisateur pour pickle. **
        """
        self.__init__(
            bbox=state["bbox"],
            spot_im=state["im"],
            distortion=state["dis"],
            diagram=None,
            identifier=state["id"])
        self.hkl = state.get("hkl", None)

class ZoneAxisPickleable:
    """
    ** Interface pour serialiser les axes. **
    """
    def __getstate__(self):
        """
        ** Recupere les informations pour reconstruir un axe. **

        Enregistre l'etat courant, ne fait pas de zele.
        """
        state = (
            tuple(self.spots.keys()),
            self.get_id(),
            *self.get_polar_coords())
        return state

    def __setstate__(self, state):
        """
        ** Initialisateur pour pickle. **
        """
        self.diagram = None
        self.spots = collections.OrderedDict(
            ((ind, None) for ind in state[0]))
        self._identifier = state[1]
        self._phi = state[2]
        self._mu = state[3]

class DiagramPickleable:
    """
    ** Interface pour serialiser un diagrame. **
    """
    def __getstate__(self):
        """
        ** Recupere les informations caracteristiques d'un diagrame. **

        Enregistre l'etat courant, ne fait pas de zele.
        """
        state = {}
        state["name"] = self.get_id()
        if not os.path.exists(self.get_id()):
            state["image"] = self.get_image_xy()

        state["spots"] = [spot.__getstate__() for spot in self]
        if self._axes:
            state["axes"] = {key: [axis.__getstate__() for axis in axes]
                for key, axes in self._axes.items()}
        return state

    def __setstate__(self, state):
        """
        ** Initialisateur pour pickle. **
        """
        from laue.spot import Spot as Spot_
        from laue.zone_axis import ZoneAxis as ZoneAxis_

        class Spot(Spot_):
            def __init__(self, *args, state=None, **kwargs):
                if state is None:
                    super().__init__(*args, **kwargs)
                else:
                    self.__setstate__(state)

        class ZoneAxis(ZoneAxis_):
            def __init__(self, *args, state=None, **kwargs):
                if state is None:
                    super().__init__(*args, **kwargs)
                else:
                    self.__setstate__(state)

        self.__init__(state["name"], None)
        self._set_image(state.get("image", None))

        self._set_spots([Spot(state=s) for s in state["spots"]])
        for spot in self:
            spot.diagram = self
        if "axes" in state:
            self._axes = {key: [ZoneAxis(state=s) for s in axes]
                for key, axes in state["axes"].items()}
        for axes in self._axes.values():
            for axis in axes:
                axis.diagram = self
                axis.spots = collections.OrderedDict(
                    ((ind, self[ind]) for ind in axis.spots.keys()))

class ExperimentPickleable:
    """
    ** Interface pour serialiser une experience. **
    """
    pass
