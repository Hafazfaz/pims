'use strict';
(function ($) {
    $(document).ready(function () {
        const $dept = $('#id_department');
        const $unit = $('#id_unit');

        function filterUnits(departmentId) {
            $unit.val(null).trigger('change'); // clear current selection
            if (!departmentId) return;

            fetch('/org/units/by-department/?department_id=' + departmentId)
                .then(r => r.json())
                .then(units => {
                    // Replace Select2 options with filtered units
                    $unit.empty();
                    $unit.append(new Option('---------', '', true, true));
                    units.forEach(u => $unit.append(new Option(u.name, u.id)));
                    $unit.trigger('change');
                });
        }

        // Select2 fires this event when value changes
        $dept.on('change', function () {
            filterUnits($(this).val());
        });

        // On page load, if department is already set, filter immediately
        if ($dept.val()) {
            filterUnits($dept.val());
        }
    });
}(django.jQuery));
