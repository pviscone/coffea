import re

import awkward
import dask_awkward
import numpy

from coffea.lookup_tools.jersf_lookup import jersf_lookup


def _checkConsistency(against, tocheck):
    if against is None:
        against = tocheck
    else:
        if against != tocheck:
            raise Exception(
                "Corrector for {} is mixed"
                "with correctors for {}!".format(tocheck, against)
            )
    return tocheck


_levelre = re.compile("SF+")


def _getLevel(levelName):
    matches = _levelre.findall(levelName)
    if len(matches) > 1:
        raise Exception(f"Malformed JERSF level name: {levelName}")
    return matches[0]


_level_order = ["SF"]


class JetResolutionScaleFactor:
    """
    This class is a columnar implementation of the JetResolutionScaleFactor tool in
    CMSSW and FWLite. It calculates the jet energy resolution scale factor for a
    corrected jet in a given binning.

    It implements the jet energy scale factor definition specified in the JER TWiki_.

    .. _TWiki: https://twiki.cern.ch/twiki/bin/view/CMS/JetResolution

    You can use this class as follows::

        jersf = JetResolutionScaleFactor(name1=corrL1,...)
        jetResSF = jersf(JetParameter1=jet.parameter1,...)

    """

    def __init__(self, **kwargs):
        """
        You construct a JetResolutionScaleFactor by passing in a dict of names and functions.
        Names must be formatted as '<campaign>_<dataera>_<datatype>_<level>_<jettype>'.
        """
        jettype = None
        levels = []
        funcs = []
        datatype = None
        campaign = None
        dataera = None
        for name, func in kwargs.items():
            if not isinstance(func, jersf_lookup):
                raise Exception(f"{name} is a {type(func)} and not a jersf_lookup!")
            info = name.split("_")
            if len(info) != 5:
                raise Exception("Corrector name is not properly formatted!")

            campaign = _checkConsistency(campaign, info[0])
            dataera = _checkConsistency(dataera, info[1])
            datatype = _checkConsistency(datatype, info[2])
            levels.append(info[3])
            funcs.append(func)
            jettype = _checkConsistency(jettype, info[4])

        if campaign is None:
            raise Exception("Unable to determine production campaign of JECs!")
        else:
            self._campaign = campaign

        if dataera is None:
            raise Exception("Unable to determine data era of JECs!")
        else:
            self._dataera = dataera

        if datatype is None:
            raise Exception("Unable to determine if JECs are for MC or Data!")
        else:
            self._datatype = datatype

        if len(levels) == 0:
            raise Exception("No levels provided?")
        else:
            self._levels = levels
            self._funcs = funcs

        if jettype is None:
            raise Exception("Unable to determine type of jet to correct!")
        else:
            self._jettype = jettype

        for i, level in enumerate(self._levels):
            this_level = _getLevel(level)
            ord_idx = _level_order.index(this_level)
            if i != this_level:
                self._levels[i], self._levels[ord_idx] = (
                    self._levels[ord_idx],
                    self._levels[i],
                )
                self._funcs[i], self._funcs[ord_idx] = (
                    self._funcs[ord_idx],
                    self._funcs[i],
                )

        # now we setup the call signature for this factorized JEC
        self._signature = []
        for func in self._funcs:
            sig = func.signature
            for input in sig:
                if input not in self._signature:
                    self._signature.append(input)

    @property
    def signature(self):
        """list the necessary jet properties that must be input to this function"""
        return self._signature

    def __repr__(self):
        out = "campaign   : %s\n" % (self._campaign)
        out += "data era   : %s\n" % (self._dataera)
        out += "data type  : %s\n" % (self._datatype)
        out += "jet type   : %s\n" % (self._jettype)
        out += "levels     : %s\n" % (",".join(self._levels))
        out += "signature  : (%s)\n" % (",".join(self._signature))
        return out

    def getScaleFactor(self, **kwargs):
        """
        Returns the set of resolutions for all input jets at the highest available level

        Use it like::

            jersfs = jersf.getScaleFactor(JetProperty1=jet.property1,...)

        """
        sfs = []
        for i, func in enumerate(self._funcs):
            sig = func.signature
            args = tuple(kwargs[inp] for inp in sig)

            if isinstance(
                args[0], (dask_awkward.Array, awkward.highlevel.Array, numpy.ndarray)
            ):
                sfs.append(
                    func(
                        *args,
                        dask_label=f"{self._campaign}-{self._dataera}-{self._datatype}-{self._levels[i]}-{self._jettype}",
                    )
                )
            else:
                raise Exception("Unknown array library for inputs.")

        return sfs[-1]
