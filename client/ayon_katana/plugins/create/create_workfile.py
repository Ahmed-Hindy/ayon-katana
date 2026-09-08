"""Creator plugin for creating workfiles."""

from ayon_core.pipeline import AutoCreator, CreatedInstance

from ayon_katana.api import context, plugin


class CreateWorkfile(plugin.KatanaCreatorBase, AutoCreator):
    """Workfile auto-creator."""

    settings_category = "katana"
    identifier = "io.ayon.creators.katana.workfile"
    label = "Workfile"
    product_base_type = "workfile"
    product_type = product_base_type
    icon = "fa5.file"

    default_variant = "Main"
    is_mandatory = False

    def create(self):
        """Create or synchronize the mandatory workfile instance."""
        variant = self.default_variant
        current_instance = next(
            (
                instance
                for instance in self.create_context.instances
                if instance.creator_identifier == self.identifier
            ),
            None,
        )

        project_entity = self.create_context.get_current_project_entity()
        folder_entity = self.create_context.get_current_folder_entity()
        task_entity = self.create_context.get_current_task_entity()

        project_name = project_entity["name"]
        folder_path = folder_entity["path"]
        task_name = task_entity["name"]
        host_name = self.create_context.host_name

        if current_instance is None:
            product_name = self.get_product_name(
                project_name=project_name,
                project_entity=project_entity,
                folder_entity=folder_entity,
                task_entity=task_entity,
                variant=variant,
                host_name=host_name,
                product_type=self.product_type,
            )
            data = {
                "folderPath": folder_path,
                "task": task_name,
                "productType": self.product_type,
                "variant": variant,
            }

            self.log.info("Auto-creating workfile instance...")
            current_instance = CreatedInstance(
                product_base_type=self.product_base_type,
                product_type=self.product_type,
                product_name=product_name,
                data=data,
                creator=self,
            )
            self._add_instance_to_context(current_instance)
        elif (
            current_instance["folderPath"] != folder_path
            or current_instance["task"] != task_name
        ):
            product_name = self.get_product_name(
                project_name=project_name,
                project_entity=project_entity,
                folder_entity=folder_entity,
                task_entity=task_entity,
                variant=variant,
                host_name=host_name,
                product_type=self.product_type,
            )
            current_instance["folderPath"] = folder_path
            current_instance["task"] = task_name
            current_instance["productType"] = self.product_type
            current_instance["productName"] = product_name

        if hasattr(current_instance, "set_mandatory"):
            current_instance.set_mandatory(self.is_mandatory)

        context.set_workfile_instance_data(current_instance.data_to_store())

    def collect_instances(self):
        """Collect the workfile instance embedded in the Katana project."""
        workfile = context.get_workfile_instance_data()
        if not workfile:
            return

        created_instance = CreatedInstance.from_existing(workfile, self)
        self._add_instance_to_context(created_instance)

    def update_instances(self, update_list):
        """Persist workfile creator-instance changes in the project."""
        for created_inst, _changes in update_list:
            if created_inst["creator_identifier"] != self.identifier:
                continue
            context.set_workfile_instance_data(created_inst.data_to_store())
