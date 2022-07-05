Editing UMI Template Files
==========================

`archetypal` can read an UMI Template File using the command:

.. code-block:: python

    from archetypal import UmiTemplateLibrary
    template_library = UmiTemplateLibrary.open("file.json")

which returns an :class:`~archetypal.umi_template.UmiTemplateLibrary` object.


Combining template libraries
----------------------------

Combine two template libraries like this:

.. code-block:: python

    from archetypal import UmiTemplateLibrary
    lib_a = UmiTemplateLibrary.open("a.json")
    lib_b = UmiTemplateLibrary.open("b.json")

    lib_c = lib_a + lib_b

The resulting `lib_c` will contain all components from both libraries. To avoid
duplicates (components that are `equal`), run:

.. code-block:: python

    lib_c.unique_components()

Plot the hierarchy of of an UmiTempalteLIbrary

.. code-block:: python

        a = UmiTemplateLibrary.open(file)
        a.unique_components()
        G = a.to_graph()
        pos = graphviz_layout(G, prog="dot", args="-s300")
        write_dot(G, "G.dot")
        fig, ax = plt.subplots(1, 1, figsize=(100,40))
        nx.draw(G, pos, with_labels=True, arrows=True, ax=ax)
        for group, values in a:
            print("rank = same; " + "; ".join((f'"{v}"' for v in values)) +";")
        plt.show()
        fig.tight_layout()
        fig.savefig("template.pdf")