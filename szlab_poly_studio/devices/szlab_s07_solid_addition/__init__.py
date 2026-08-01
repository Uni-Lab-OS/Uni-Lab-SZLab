from importlib import import_module

SZLabS07SolidAdditionDevice = import_module(__name__ + ".device").SZLabS07SolidAdditionDevice
__all__ = ["SZLabS07SolidAdditionDevice"]
