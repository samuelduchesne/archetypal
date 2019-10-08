{{ fullname | escape | underline}}


.. currentmodule:: {{ module }}

.. auto{{ objtype }}:: {{ objname }} {% if objtype in ['class'] %}
   :members:
   :inherited-members:
   {% endif %}



