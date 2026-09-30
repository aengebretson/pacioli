# Resolve both cache entries (-D) and normal variables supplied by a parent.
# Do not cache a generated counterpart: a legacy-only cache must remain usable
# when its caller changes PACIOLI_* on a subsequent configure.
function(luca_compatible_option suffix description default_value)
  set(canonical "LUCA_${suffix}")
  set(legacy "PACIOLI_${suffix}")
  if(DEFINED ${canonical} AND DEFINED ${legacy})
    if((${canonical} AND NOT ${legacy}) OR (${legacy} AND NOT ${canonical}))
      message(FATAL_ERROR
        "Conflicting LUCA options: ${canonical}=${${canonical}} and "
        "${legacy}=${${legacy}}. Set both to the same boolean value, or remove "
        "the obsolete cache entry with cmake -U${legacy} (or -U${canonical}). "
        "Parent projects must also remove any conflicting normal variable.")
    endif()
  endif()

  if(DEFINED ${legacy} AND NOT DEFINED ${canonical})
    set(${canonical} "${${legacy}}")
  else()
    option(${canonical} "${description}" "${default_value}")
  endif()
  # Keep the legacy variable readable without creating a stale cache alias.
  set(${canonical} "${${canonical}}" PARENT_SCOPE)
  set(${legacy} "${${canonical}}" PARENT_SCOPE)
endfunction()
